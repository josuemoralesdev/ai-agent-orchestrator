from __future__ import annotations

import os
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.execution.binance_futures_connector import (
    LIVE_ORDER_ENABLED,
    TEST_ORDER_ONLY,
    append_connector_attempt,
    append_protective_attempt,
)
from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.first_live_runbook import (
    ENABLEMENT_PLAN_READY,
    GO_FOR_ENABLEMENT_PLAN,
    LOCKED_AFTER_ATTEMPT,
    NO_GO,
    WAITING_FOR_EXACT_APPROVAL,
    WAITING_FOR_PROMOTED_SIGNAL,
    WAITING_FOR_PROTECTIVE_READY,
    WAITING_FOR_TEST_ORDER,
    build_first_live_runbook,
    evaluate_first_live_runbook,
    first_live_runbook_evaluations_path,
    load_first_live_runbook_evaluations,
)
from src.app.hammer_radar.operator.live_approval import append_live_approval_request
from src.app.hammer_radar.operator.live_preflight import PREFLIGHT_READY_BUT_EXECUTION_DISABLED, PROMOTED_STRATEGY_KEY
from src.app.hammer_radar.operator.operator_actions import parse_operator_action
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR


class FirstLiveRunbookTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict("os.environ", {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False)
        self.env_patch.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_default_runbook_returns_no_go_waiting_for_promoted_signal(self) -> None:
        payload = build_first_live_runbook(log_dir=self.log_dir)

        self.assertEqual(NO_GO, payload["gate_decision"])
        self.assertEqual(WAITING_FOR_PROMOTED_SIGNAL, payload["runbook_status"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["secrets_shown"])

    def test_missing_exact_approval_blocks(self) -> None:
        payload = build_first_live_runbook(preflight_pack=self._ready_pack(), log_dir=self.log_dir)

        self.assertEqual(WAITING_FOR_EXACT_APPROVAL, payload["runbook_status"])
        self.assertEqual(NO_GO, payload["gate_decision"])
        self.assertFalse(payload["checklist"]["exact_live_approval_found"]["passed"])

    def test_missing_test_order_validation_blocks(self) -> None:
        self._append_exact_approval("BTCUSDT|13m|long|ready")

        payload = build_first_live_runbook(preflight_pack=self._ready_pack(), log_dir=self.log_dir)

        self.assertEqual(WAITING_FOR_TEST_ORDER, payload["runbook_status"])
        self.assertFalse(payload["checklist"]["test_order_validated_for_signal"]["passed"])

    def test_missing_protective_readiness_blocks(self) -> None:
        self._append_exact_approval("BTCUSDT|13m|long|ready")
        self._append_test_order_validated("BTCUSDT|13m|long|ready")

        payload = build_first_live_runbook(preflight_pack=self._ready_pack(), log_dir=self.log_dir)

        self.assertEqual(WAITING_FOR_PROTECTIVE_READY, payload["runbook_status"])
        self.assertFalse(payload["checklist"]["protective_orders_ready"]["passed"])
        self.assertFalse(payload["checklist"]["no_naked_entry"]["passed"])

    def test_all_non_env_gates_mocked_pass_to_go_for_enablement_plan(self) -> None:
        self._append_exact_approval("BTCUSDT|13m|long|ready")
        self._append_test_order_validated("BTCUSDT|13m|long|ready")
        self._append_protective_ready("BTCUSDT|13m|long|ready")

        payload = build_first_live_runbook(preflight_pack=self._ready_pack(), log_dir=self.log_dir)

        self.assertEqual(ENABLEMENT_PLAN_READY, payload["runbook_status"])
        self.assertEqual(GO_FOR_ENABLEMENT_PLAN, payload["gate_decision"])
        self.assertTrue(payload["checklist"]["protective_orders_ready"]["passed"])
        self.assertFalse(payload["checklist"]["live_execution_enabled"]["passed"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertGreater(len(payload["enablement_plan"]), 0)
        self.assertIn("Immediately restore HAMMER_LIVE_EXECUTION_ENABLED=false.", payload["enablement_plan"])
        self.assertIn("Verify system locked again.", payload["enablement_plan"])

    def test_locked_after_attempt_blocks(self) -> None:
        self._append_live_order_attempt("BTCUSDT|13m|long|ready")

        payload = build_first_live_runbook(preflight_pack=self._ready_pack(), log_dir=self.log_dir)

        self.assertEqual(LOCKED_AFTER_ATTEMPT, payload["runbook_status"])
        self.assertEqual(NO_GO, payload["gate_decision"])
        self.assertFalse(payload["checklist"]["no_duplicate_signal_order"]["passed"])

    def test_evaluate_persists_and_dedupes_identical_snapshot(self) -> None:
        first = evaluate_first_live_runbook(log_dir=self.log_dir)
        second = evaluate_first_live_runbook(log_dir=self.log_dir)
        records = load_first_live_runbook_evaluations(limit=10, log_dir=self.log_dir)

        self.assertTrue(first["recorded"])
        self.assertFalse(second["recorded"])
        self.assertEqual(first["evaluation_id"], second["existing_evaluation_id"])
        self.assertEqual(1, len(records))
        self.assertTrue(first_live_runbook_evaluations_path(self.log_dir).exists())

    def test_runbook_does_not_modify_env_or_place_order_or_call_network(self) -> None:
        before = dict(os.environ)
        with patch("urllib.request.urlopen") as urlopen:
            payload = build_first_live_runbook(preflight_pack=self._ready_pack(), log_dir=self.log_dir)

        self.assertEqual(before, dict(os.environ))
        urlopen.assert_not_called()
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])

    def test_operator_parser_recognizes_first_live_commands(self) -> None:
        for text in ("FIRST LIVE CHECK", "FIRST LIVE RUNBOOK", "FIRST LIVE EVALUATE"):
            with self.subTest(text=text):
                payload = parse_operator_action(text)
                self.assertEqual("first_live_check", payload["normalized_action"])
                self.assertEqual("ACCEPTED", payload["result_status"])
                self.assertFalse(payload["order_placed"])

    def test_api_endpoints_return_safety_flags_and_records(self) -> None:
        runbook = self.client.get("/first-live/runbook")
        evaluate = self.client.post("/first-live/evaluate", json={})
        records = self.client.get("/first-live/evaluations")

        self.assertEqual(200, runbook.status_code)
        self.assertEqual(NO_GO, runbook.json()["gate_decision"])
        self.assertFalse(runbook.json()["order_placed"])
        self.assertFalse(runbook.json()["real_order_placed"])
        self.assertEqual(200, evaluate.status_code)
        self.assertTrue(evaluate.json()["recorded"])
        self.assertFalse(evaluate.json()["secrets_shown"])
        self.assertEqual(200, records.status_code)
        self.assertEqual(1, len(records.json()["first_live_runbook_evaluations"]))

    def test_operator_actions_first_live_check_records_runbook(self) -> None:
        response = self.client.post("/operator/actions", json={"text": "FIRST LIVE CHECK"})
        payload = response.json()

        self.assertEqual(200, response.status_code)
        self.assertEqual(NO_GO, payload["gate_decision"])
        self.assertEqual("first_live_check", payload["operator_action"]["normalized_action"])
        self.assertFalse(payload["order_placed"])

    def test_operator_latest_includes_first_live_evaluation(self) -> None:
        evaluation = self.client.post("/first-live/evaluate", json={}).json()
        latest = self.client.get("/operator/latest").json()

        self.assertEqual(evaluation["evaluation_id"], latest["latest_first_live_runbook_evaluation"]["evaluation_id"])

    def test_ui_docs_safety_text_exists(self) -> None:
        html = self.client.get("/ui").text

        self.assertIn("First Live Runbook", html)
        self.assertIn("Runbook only.", html)
        self.assertIn("Does not flip env.", html)
        self.assertIn("Does not place orders.", html)
        self.assertIn("Lock back down after one attempt.", html)

    def _append_exact_approval(self, signal_id: str) -> None:
        append_live_approval_request(
            {
                "request_id": f"approval-{signal_id}",
                "created_at": datetime.now(UTC).isoformat(),
                "source": "test",
                "raw_text": f"LIVE APPROVE {signal_id}",
                "normalized_action": "live_approve_exact",
                "parse_status": "ACCEPTED",
                "approval_gate_status": "READY_BUT_EXECUTION_DISABLED",
                "signal_id": signal_id,
                "order_placed": False,
                "execution_attempted": False,
                "order_payload_created": False,
            },
            log_dir=self.log_dir,
        )

    def _append_test_order_validated(self, signal_id: str) -> None:
        append_connector_attempt(
            {
                "attempt_id": f"test-order-{signal_id}",
                "created_at": datetime.now(UTC).isoformat(),
                "endpoint": "test_order",
                "action": "test_order",
                "connector_mode": TEST_ORDER_ONLY,
                "signal_id": signal_id,
                "preflight_id": "preflight-ready",
                "status": "TEST_ORDER_MOCK_VALIDATED",
                "blockers": [],
                "network_used": False,
                "order_payload_created": True,
                "signed_payload_created": True,
                "execution_attempted": True,
                "order_placed": False,
                "real_order_placed": False,
                "mock_order_placed": False,
                "live_execution_enabled": False,
                "allow_live_orders": False,
                "global_kill_switch": True,
                "secrets_shown": False,
            },
            log_dir=self.log_dir,
        )

    def _append_protective_ready(self, signal_id: str) -> None:
        append_protective_attempt(
            {
                "attempt_id": f"protective-{signal_id}",
                "created_at": datetime.now(UTC).isoformat(),
                "endpoint": "protective_test",
                "action": "protective_test",
                "connector_mode": LIVE_ORDER_ENABLED,
                "protective_order_mode": "TEST_ONLY",
                "signal_id": signal_id,
                "preflight_id": "preflight-ready",
                "strategy_key": PROMOTED_STRATEGY_KEY,
                "status": "PROTECTIVE_TEST_MOCK_VALIDATED",
                "blockers": [],
                "network_used": False,
                "signed_payload_created": True,
                "order_payload_created": True,
                "protective_orders_sent": False,
                "stop_order_payload_created": True,
                "take_profit_order_payload_created": True,
                "execution_attempted": True,
                "order_placed": False,
                "real_order_placed": False,
                "live_execution_enabled": False,
                "allow_live_orders": False,
                "global_kill_switch": True,
                "secrets_shown": False,
            },
            log_dir=self.log_dir,
        )

    def _append_live_order_attempt(self, signal_id: str) -> None:
        append_connector_attempt(
            {
                "attempt_id": f"live-{signal_id}",
                "created_at": datetime.now(UTC).isoformat(),
                "endpoint": "execute",
                "action": "execute",
                "connector_mode": LIVE_ORDER_ENABLED,
                "signal_id": signal_id,
                "preflight_id": "preflight-ready",
                "status": "LIVE_ORDER_SENT",
                "blockers": [],
                "network_used": True,
                "order_payload_created": True,
                "execution_attempted": True,
                "order_placed": True,
                "real_order_placed": True,
                "mock_order_placed": False,
                "live_execution_enabled": True,
                "allow_live_orders": True,
                "global_kill_switch": False,
                "secrets_shown": False,
            },
            log_dir=self.log_dir,
        )

    @staticmethod
    def _ready_pack() -> dict:
        signal_id = "BTCUSDT|13m|long|ready"
        return {
            "preflight_id": "preflight-ready",
            "preflight_status": PREFLIGHT_READY_BUT_EXECUTION_DISABLED,
            "promoted_strategy_ready": True,
            "matching_fresh_signal_found": True,
            "strategy_key": PROMOTED_STRATEGY_KEY,
            "candidate_signal_id": signal_id,
            "signal_id": signal_id,
            "readiness_status": "READY",
            "ticket_status": "PROPOSED",
            "dry_run_status": "VALID",
            "live_safety_status": "WOULD_BE_ALLOWED_IF_LIVE_ENABLED",
            "candidate": {
                "signal_id": signal_id,
                "symbol": "BTCUSDT",
                "timeframe": "13m",
                "direction": "long",
                "entry": 100.0,
                "stop": 95.0,
                "take_profit": 105.0,
                "freshness_status": "fresh",
                "decision": "ELIGIBLE_TINY_LIVE",
                "tradable": True,
                "reject_reason": None,
            },
        }


if __name__ == "__main__":
    unittest.main()
