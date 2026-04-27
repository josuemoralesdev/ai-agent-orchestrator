from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator import archive
from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.models import SignalRecord
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR


class ApprovalApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict("os.environ", {LOG_DIR_ENV_VAR: str(self.log_dir)})
        self.env_patch.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_health_returns_live_execution_disabled(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual("hammer_radar_approval_api", payload["service"])
        self.assertFalse(payload["live_execution_enabled"])

    def test_ui_returns_html_with_safety_text_and_buttons(self) -> None:
        for path in ("/", "/ui"):
            response = self.client.get(path)

            self.assertEqual(200, response.status_code)
            self.assertIn("text/html", response.headers["content-type"])
            html = response.text
            self.assertIn("live_execution_enabled=false", html)
            self.assertIn("Record Decision", html)
            self.assertIn("Watch", html)
            self.assertIn("Reject", html)
            self.assertIn("Paper Only", html)
            self.assertIn("Approve Manual Live", html)
            self.assertIn("No order placement", html)

    def test_candidates_returns_live_execution_disabled_and_decisions(self) -> None:
        archive.append_signal(self._eligible_signal(signal_id="eligible|1"), log_dir=self.log_dir)

        response = self.client.get("/candidates")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertFalse(payload["live_execution_enabled"])
        self.assertFalse(payload["order_placed"])
        self.assertEqual("ELIGIBLE_TINY_LIVE", payload["candidates"][0]["decision"])
        self.assertFalse(payload["candidates"][0]["order_placed"])

    def test_approve_manual_live_records_decision_for_eligible_candidate(self) -> None:
        archive.append_signal(self._eligible_signal(signal_id="eligible|approve"), log_dir=self.log_dir)

        response = self.client.post(
            "/decisions",
            json={
                "signal_id": "eligible|approve",
                "decision": "approve_manual_live",
                "operator": "josue",
                "notes": "manual intent only",
                "intended_position_usd": 44,
                "intended_leverage": 2,
            },
        )

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("approve_manual_live", payload["decision"])
        self.assertFalse(payload["live_execution_enabled"])
        self.assertFalse(payload["order_placed"])
        self.assertEqual("ELIGIBLE_TINY_LIVE", payload["candidate_snapshot"]["decision"])
        self.assertTrue((self.log_dir / "manual_decisions.ndjson").exists())

    def test_reject_records_decision(self) -> None:
        response = self.client.post(
            "/decisions",
            json={
                "signal_id": "unknown|reject",
                "decision": "reject",
                "operator": "josue",
                "notes": "not interested",
            },
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual("reject", response.json()["decision"])

    def test_paper_only_records_decision(self) -> None:
        response = self.client.post(
            "/decisions",
            json={
                "signal_id": "unknown|paper",
                "decision": "paper_only",
                "operator": "josue",
                "notes": "paper only",
            },
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual("paper_only", response.json()["decision"])

    def test_approve_manual_live_rejects_forbidden_candidate(self) -> None:
        archive.append_signal(
            self._eligible_signal(
                signal_id="forbidden|1",
                tradable=False,
                reject_reason="strength_below_minimum",
                hammer_strength=60.0,
            ),
            log_dir=self.log_dir,
        )

        response = self.client.post(
            "/decisions",
            json={
                "signal_id": "forbidden|1",
                "decision": "approve_manual_live",
                "operator": "josue",
                "notes": "should fail",
                "override_reason": "still should not approve forbidden",
            },
        )

        self.assertEqual(400, response.status_code)
        self.assertIn("FORBIDDEN", response.json()["detail"])

    def test_approval_over_default_max_position_fails_unless_override_reason_provided(self) -> None:
        archive.append_signal(self._eligible_signal(signal_id="eligible|position"), log_dir=self.log_dir)

        failed = self.client.post(
            "/decisions",
            json={
                "signal_id": "eligible|position",
                "decision": "approve_manual_live",
                "operator": "josue",
                "intended_position_usd": 45,
            },
        )
        allowed = self.client.post(
            "/decisions",
            json={
                "signal_id": "eligible|position",
                "decision": "approve_manual_live",
                "operator": "josue",
                "intended_position_usd": 45,
                "override_reason": "manual cap exception",
            },
        )

        self.assertEqual(400, failed.status_code)
        self.assertEqual(200, allowed.status_code)

    def test_approval_over_default_max_leverage_fails_unless_override_reason_provided(self) -> None:
        archive.append_signal(self._eligible_signal(signal_id="eligible|leverage"), log_dir=self.log_dir)

        failed = self.client.post(
            "/decisions",
            json={
                "signal_id": "eligible|leverage",
                "decision": "approve_manual_live",
                "operator": "josue",
                "intended_leverage": 4,
            },
        )
        allowed = self.client.post(
            "/decisions",
            json={
                "signal_id": "eligible|leverage",
                "decision": "approve_manual_live",
                "operator": "josue",
                "intended_leverage": 4,
                "override_reason": "manual leverage exception",
            },
        )

        self.assertEqual(400, failed.status_code)
        self.assertEqual(200, allowed.status_code)

    def test_decisions_are_stored_in_selected_log_dir_and_listed(self) -> None:
        response = self.client.post(
            "/decisions",
            json={
                "signal_id": "list|1",
                "decision": "watch",
                "operator": "josue",
                "notes": "watching",
            },
        )
        decision_id = response.json()["decision_id"]

        list_response = self.client.get("/decisions")
        single_response = self.client.get(f"/decisions/{decision_id}")

        self.assertEqual(200, list_response.status_code)
        self.assertEqual(1, len(list_response.json()["decisions"]))
        self.assertEqual(200, single_response.status_code)
        self.assertEqual(decision_id, single_response.json()["decision_id"])
        self.assertTrue((self.log_dir / "manual_decisions.ndjson").exists())

    def test_no_live_order_placement_fields_are_true(self) -> None:
        response = self.client.post(
            "/decisions",
            json={
                "signal_id": "safe|1",
                "decision": "watch",
                "operator": "josue",
            },
        )

        payload = response.json()
        self.assertFalse(payload["live_execution_enabled"])
        self.assertFalse(payload["order_placed"])

    @staticmethod
    def _eligible_signal(
        *,
        signal_id: str,
        tradable: bool = True,
        reject_reason: str | None = None,
        hammer_strength: float = 100.0,
    ) -> SignalRecord:
        return SignalRecord(
            signal_id=signal_id,
            symbol="BTCUSDT",
            timeframe="13m",
            direction="long",
            timestamp=(datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
            hammer_strength=hammer_strength,
            hammer_high=101.0,
            hammer_low=94.0,
            fib_50=100.5,
            fib_618=100.0,
            fib_650=99.5,
            fib_786=98.5,
            invalidation=95.0,
            bias_timeframe="4H",
            bias_direction="bullish",
            bias_aligned=True,
            same_direction_streak=0,
            opposite_direction_streak=0,
            tradable=tradable,
            reject_reason=reject_reason,
            trend_direction="bullish",
            trend_strength_score=0.4,
            trend_lookback_candles=3,
            ema_4h_20=100.0,
            price_vs_ema_4h_pct=0.1,
            signal_close=100.0,
            rsi_value=50.0,
            rsi_state="neutral",
            divergence_type="bullish",
            divergence_confirmed=True,
        )


if __name__ == "__main__":
    unittest.main()
