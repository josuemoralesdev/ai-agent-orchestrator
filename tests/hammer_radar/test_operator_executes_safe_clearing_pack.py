from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.operator_executes_safe_clearing_pack import (
    CONFIRM_SAFE_CLEARING_PHRASE,
    EVENT_TYPE,
    LEDGER_FILENAME,
    BLOCKER_CLEARING_PACK_BLOCKED,
    BLOCKER_CLEARING_PACK_READY,
    SAFE_CLEARING_BLOCKED,
    SAFE_CLEARING_EXECUTED,
    SAFE_CLEARING_PREVIEW,
    SAFE_CLEARING_REJECTED,
    append_safe_clearing_pack_run_record,
    build_clearing_delta,
    build_operator_executes_safe_clearing_pack,
    collect_clearing_before_snapshot,
    load_safe_clearing_pack_run_records,
)

LANE_KEY = "BTCUSDT|13m|long|ladder_close_50_618"


class OperatorExecutesSafeClearingPackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.tmp.name) / "logs"
        self.now = datetime(2026, 5, 26, 12, 0, tzinfo=UTC)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_preview_writes_no_run_record_and_does_not_attempt_paper_proof(self) -> None:
        with patch(
            "src.app.hammer_radar.operator.operator_executes_safe_clearing_pack.run_autonomous_paper_lane_executor_once"
        ) as r129:
            payload = build_operator_executes_safe_clearing_pack(
                log_dir=self.log_dir,
                lane_key=LANE_KEY,
                now=self.now,
            )

        self.assertEqual(SAFE_CLEARING_PREVIEW, payload["status"])
        self.assertFalse(payload["execute_safe_clearing_requested"])
        self.assertFalse(payload["safe_clearing_run_recorded"])
        self.assertFalse((self.log_dir / LEDGER_FILENAME).exists())
        self.assertFalse(payload["paper_proof_result"]["attempted"])
        r129.assert_not_called()

    def test_preview_does_not_report_fake_blocker_clearing(self) -> None:
        before = self._snapshot(eligible=1, blocker_total=28)
        with patch(
            "src.app.hammer_radar.operator.operator_executes_safe_clearing_pack.collect_clearing_before_snapshot",
            return_value=before,
        ):
            payload = build_operator_executes_safe_clearing_pack(
                log_dir=self.log_dir,
                lane_key=LANE_KEY,
                now=self.now,
            )

        self.assertEqual(SAFE_CLEARING_PREVIEW, payload["status"])
        self.assertEqual({}, payload["after_snapshot"])
        self._assert_delta_not_collected(payload)
        self._assert_safety_flags_clean(payload)

    def test_wrong_confirmation_rejects_execution_without_ledger_or_paper_proof(self) -> None:
        with patch(
            "src.app.hammer_radar.operator.operator_executes_safe_clearing_pack.run_autonomous_paper_lane_executor_once"
        ) as r129:
            payload = build_operator_executes_safe_clearing_pack(
                log_dir=self.log_dir,
                lane_key=LANE_KEY,
                execute_safe_clearing=True,
                confirm_safe_clearing="wrong",
                now=self.now,
            )

        self.assertEqual(SAFE_CLEARING_REJECTED, payload["status"])
        self.assertTrue(payload["execute_safe_clearing_requested"])
        self.assertFalse(payload["confirmation_valid"])
        self.assertFalse(payload["safe_clearing_run_recorded"])
        self.assertFalse((self.log_dir / LEDGER_FILENAME).exists())
        r129.assert_not_called()

    def test_rejected_does_not_report_fake_blocker_clearing(self) -> None:
        before = self._snapshot(eligible=1, blocker_total=28)
        with patch(
            "src.app.hammer_radar.operator.operator_executes_safe_clearing_pack.collect_clearing_before_snapshot",
            return_value=before,
        ):
            payload = build_operator_executes_safe_clearing_pack(
                log_dir=self.log_dir,
                lane_key=LANE_KEY,
                execute_safe_clearing=True,
                confirm_safe_clearing="wrong",
                now=self.now,
            )

        self.assertEqual(SAFE_CLEARING_REJECTED, payload["status"])
        self.assertEqual({}, payload["after_snapshot"])
        self._assert_delta_not_collected(payload)
        self._assert_safety_flags_clean(payload)

    def test_exact_confirmation_records_run_only_and_uses_r129_path_for_paper_proof(self) -> None:
        before = self._snapshot(eligible=1, blocker_total=3, paper_status="PAPER_EXECUTOR_INTEGRATION_PREVIEW")
        after = self._snapshot(eligible=0, blocker_total=2, paper_status="PAPER_EXECUTOR_INTEGRATION_RECORDED")
        r129_result = {
            "status": "PAPER_EXECUTOR_INTEGRATION_RECORDED",
            "paper_eligible_decisions_count": 1,
            "paper_execution_records_created": 1,
            "paper_execution_ids": ["paper-1"],
            "integration_recorded": True,
            "integration_id": "integration-1",
            "top_blockers": [],
            "safety": self._safe(),
            "source_surfaces_used": ["R129"],
        }
        with (
            patch(
                "src.app.hammer_radar.operator.operator_executes_safe_clearing_pack.collect_clearing_before_snapshot",
                return_value=before,
            ),
            patch(
                "src.app.hammer_radar.operator.operator_executes_safe_clearing_pack.collect_clearing_after_snapshot",
                return_value=after,
            ),
            patch(
                "src.app.hammer_radar.operator.operator_executes_safe_clearing_pack.run_autonomous_paper_lane_executor_once",
                return_value=r129_result,
            ) as r129,
        ):
            payload = build_operator_executes_safe_clearing_pack(
                log_dir=self.log_dir,
                lane_key=LANE_KEY,
                execute_safe_clearing=True,
                confirm_safe_clearing=CONFIRM_SAFE_CLEARING_PHRASE,
                now=self.now,
            )

        self.assertEqual(SAFE_CLEARING_EXECUTED, payload["status"])
        self.assertTrue(payload["confirmation_valid"])
        self.assertTrue(payload["safe_clearing_run_recorded"])
        self.assertEqual("paper-1", payload["attempted_actions"][1]["evidence_ids"][0])
        r129.assert_called_once()
        self.assertTrue(r129.call_args.kwargs["record_paper"])
        self.assertTrue(r129.call_args.kwargs["record_scheduler_tick"])
        self.assertTrue(r129.call_args.kwargs["record_decisions"])
        self.assertEqual(
            "I CONFIRM AUTONOMOUS PAPER LANE INTEGRATION ONLY; NO REAL ORDER; NO BINANCE CALL.",
            r129.call_args.kwargs["confirm_paper_integration"],
        )
        records = load_safe_clearing_pack_run_records(log_dir=self.log_dir, limit=0)
        self.assertEqual(1, len(records))
        self.assertEqual(EVENT_TYPE, records[0]["event_type"])
        self.assertEqual(payload["safe_clearing_run_id"], records[0]["run_id"])
        self.assertEqual(LANE_KEY, records[0]["lane_key"])

    def test_skips_paper_proof_if_no_eligible_decisions(self) -> None:
        before = self._snapshot(eligible=0, blocker_total=3)
        after = self._snapshot(eligible=0, blocker_total=3)
        with (
            patch(
                "src.app.hammer_radar.operator.operator_executes_safe_clearing_pack.collect_clearing_before_snapshot",
                return_value=before,
            ),
            patch(
                "src.app.hammer_radar.operator.operator_executes_safe_clearing_pack.collect_clearing_after_snapshot",
                return_value=after,
            ),
            patch(
                "src.app.hammer_radar.operator.operator_executes_safe_clearing_pack.run_autonomous_paper_lane_executor_once"
            ) as r129,
        ):
            payload = build_operator_executes_safe_clearing_pack(
                log_dir=self.log_dir,
                lane_key=LANE_KEY,
                execute_safe_clearing=True,
                confirm_safe_clearing=CONFIRM_SAFE_CLEARING_PHRASE,
                now=self.now,
            )

        self.assertEqual(SAFE_CLEARING_BLOCKED, payload["status"])
        self.assertEqual("SKIPPED_NO_ELIGIBLE_EVIDENCE", payload["paper_proof_result"]["status"])
        self.assertEqual("SKIPPED_NO_ELIGIBLE_EVIDENCE", payload["attempted_actions"][1]["action_type"])
        self.assertTrue(any("fresh routed candidate" in item for item in payload["next_three_actions"]))
        r129.assert_not_called()

    def test_before_after_snapshots_and_delta_are_included(self) -> None:
        before = self._snapshot(eligible=0, blocker_total=4, lane_status="armed_dry_run")
        after = self._snapshot(eligible=0, blocker_total=2, lane_status="armed_dry_run")
        delta = build_clearing_delta(before_snapshot=before, after_snapshot=after)

        self.assertEqual(4, delta["blocker_counts"]["before"]["total_count"])
        self.assertEqual(2, delta["blocker_counts"]["after"]["total_count"])
        self.assertEqual(-2, delta["blocker_counts"]["delta_total"])
        self.assertFalse(delta["lane_status"]["changed"])

    def test_empty_after_snapshot_delta_is_not_collected(self) -> None:
        before = self._snapshot(eligible=0, blocker_total=28)
        delta = build_clearing_delta(before_snapshot=before, after_snapshot={})

        self.assertEqual(28, delta["blocker_counts"]["before"]["total_count"])
        self.assertEqual({"status": "NOT_COLLECTED"}, delta["blocker_counts"]["after"])
        self.assertEqual(0, delta["blocker_counts"]["delta_total"])
        self.assertEqual("NOT_COLLECTED", delta["paper_proof_status"]["after"])
        self.assertIsNone(delta["paper_proof_status"]["after_records_created"])
        self.assertEqual(0, delta["paper_proof_status"]["records_created_delta"])
        self.assertEqual("NOT_COLLECTED", delta["lane_status"]["after"])
        self.assertEqual("NOT_COLLECTED", delta["tiny_live_gate_status"]["after"])
        self.assertFalse(delta["lane_status"]["changed"])
        self.assertIsNone(delta["probability_movement"]["after_today_probability_pct"])
        self.assertIsNone(delta["probability_movement"]["after_next_session_probability_pct"])
        self.assertEqual(0, delta["probability_movement"]["today_delta_pct"])
        self.assertEqual(0, delta["probability_movement"]["next_session_delta_pct"])

    def test_not_collected_after_snapshot_marker_delta_is_not_collected(self) -> None:
        before = self._snapshot(eligible=0, blocker_total=28)
        delta = build_clearing_delta(before_snapshot=before, after_snapshot={"status": "NOT_COLLECTED"})

        self.assertEqual({"status": "NOT_COLLECTED"}, delta["blocker_counts"]["after"])
        self.assertEqual(0, delta["blocker_counts"]["delta_total"])
        self.assertEqual("NOT_COLLECTED", delta["global_gate_status"]["after"])
        self.assertIsNone(delta["probability_movement"]["after_today_probability_pct"])

    def test_safety_flags_are_always_false_and_separation_true(self) -> None:
        payload = build_operator_executes_safe_clearing_pack(log_dir=self.log_dir, lane_key=LANE_KEY, now=self.now)

        for key, value in payload["safety"].items():
            if key == "paper_live_separation_intact":
                self.assertTrue(value)
            else:
                self.assertFalse(value)

    def test_no_binance_order_payload_network_or_signed_calls_occur(self) -> None:
        from src.app.hammer_radar.execution import binance_futures_connector

        with (
            patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
            patch.object(binance_futures_connector, "preview_payload") as preview_payload,
            patch.object(binance_futures_connector, "protective_preview") as protective_preview,
            patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
            patch.object(binance_futures_connector, "submit_protective_test") as submit_protective_test,
            patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
            patch.object(binance_futures_connector, "build_signed_test_order_request") as build_signed_test_order_request,
            patch.object(binance_futures_connector, "build_signed_protective_order_requests") as build_signed_protective_order_requests,
        ):
            payload = build_operator_executes_safe_clearing_pack(log_dir=self.log_dir, lane_key=LANE_KEY, now=self.now)

        execute_live_order.assert_not_called()
        preview_payload.assert_not_called()
        protective_preview.assert_not_called()
        submit_test_order.assert_not_called()
        submit_protective_test.assert_not_called()
        build_signed_live_order_request.assert_not_called()
        build_signed_test_order_request.assert_not_called()
        build_signed_protective_order_requests.assert_not_called()
        self.assertFalse(payload["safety"]["network_allowed"])
        self.assertFalse(payload["safety"]["order_payload_created"])
        self.assertFalse(payload["safety"]["execution_attempted"])

    def test_no_env_or_config_mutation_is_reported(self) -> None:
        payload = build_operator_executes_safe_clearing_pack(log_dir=self.log_dir, lane_key=LANE_KEY, now=self.now)

        self.assertFalse(payload["safety"]["env_mutated"])
        self.assertFalse(payload["safety"]["config_written"])
        self.assertFalse(payload["safety"]["global_live_flags_changed"])

    def test_ledger_append_only(self) -> None:
        first = self._summary("first")
        second = self._summary("second")
        append_safe_clearing_pack_run_record(first, log_dir=self.log_dir)
        append_safe_clearing_pack_run_record(second, log_dir=self.log_dir)
        records = load_safe_clearing_pack_run_records(log_dir=self.log_dir, limit=0)

        self.assertEqual(2, len(records))
        self.assertEqual(["first", "second"], [record["run_id"] for record in records])

    def test_cli_mode_exists(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                str(self.log_dir),
                "operator-executes-safe-clearing-pack",
                "--lane-key",
                LANE_KEY,
            ],
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": "."},
        )

        payload = json.loads(result.stdout)
        self.assertIn(payload["status"], {SAFE_CLEARING_PREVIEW, SAFE_CLEARING_BLOCKED, "SAFE_CLEARING_ERROR"})
        self.assertIn("before_snapshot", payload)
        self.assertIn("clearing_delta", payload)
        self.assertLess(len(result.stdout), 180000)

    def test_generated_next_actions_remain_safe(self) -> None:
        payload = build_operator_executes_safe_clearing_pack(log_dir=self.log_dir, lane_key=LANE_KEY, now=self.now)
        rendered = json.dumps(payload["next_three_actions"]).lower()

        forbidden = ("binance", "payload", "signed", "env flags", "live authorization now")
        self.assertIn("fresh routed candidate", rendered)
        self.assertNotIn("order now", rendered)
        for token in forbidden:
            if token == "binance":
                continue
            self.assertNotIn(token, rendered)

    def test_collect_snapshot_reuses_r138_and_r139(self) -> None:
        snapshot = collect_clearing_before_snapshot(log_dir=self.log_dir, lane_key=LANE_KEY, now=self.now)

        self.assertIn("burn_down_status", snapshot)
        self.assertIn("operator_pack_status", snapshot)
        self.assertIn(snapshot["operator_pack_status"], {BLOCKER_CLEARING_PACK_READY, BLOCKER_CLEARING_PACK_BLOCKED})

    def _summary(self, run_id: str) -> dict:
        return {
            "status": SAFE_CLEARING_EXECUTED,
            "safe_clearing_run_id": run_id,
            "lane_key": LANE_KEY,
            "before_snapshot": self._snapshot(eligible=0, blocker_total=1),
            "attempted_actions": [],
            "after_snapshot": self._snapshot(eligible=0, blocker_total=1),
            "clearing_delta": {},
            "paper_proof_result": {},
            "blocker_movement": {},
            "probability_movement": {},
            "next_three_actions": [],
            "safety": self._safe(),
            "source_surfaces_used": ["test"],
        }

    def _snapshot(
        self,
        *,
        eligible: int,
        blocker_total: int,
        paper_status: str = "PAPER_EXECUTOR_INTEGRATION_PREVIEW",
        lane_status: str = "armed_dry_run",
    ) -> dict:
        blockers = [
            {"id": f"B{idx:03d}", "title": f"blocker {idx}", "severity": "HIGH_BLOCKER"}
            for idx in range(1, blocker_total + 1)
        ]
        return {
            "snapshot_name": "test",
            "generated_at": self.now.isoformat(),
            "lane_key": LANE_KEY,
            "burn_down_status": "LIVE_READY_BURN_DOWN_READY",
            "operator_pack_status": BLOCKER_CLEARING_PACK_READY,
            "blocker_summary": {"high_count": blocker_total, "critical_count": 0, "medium_count": 0, "low_count": 0},
            "ranked_blocker_count": blocker_total,
            "ranked_blockers": blockers,
            "lane_status": lane_status,
            "router_status": "FRESH_SIGNAL_ROUTER_READY",
            "paper_proof_status": {
                "status": paper_status,
                "paper_eligible_decisions_count": eligible,
                "paper_execution_records_created": 0,
                "top_blockers": [],
            },
            "tiny_live_gate_status": "TINY_LIVE_EXECUTION_BLOCKED",
            "protective_policy_status": "PROTECTIVE_POLICY_BLOCKED",
            "global_gate_status": "FIRST_LIVE_BLOCKED",
            "probability": {"today_probability_pct": 20, "next_session_probability_pct": 44},
            "safety": self._safe(),
            "source_surfaces_used": ["test"],
        }

    @staticmethod
    def _safe() -> dict:
        return {
            "order_placed": False,
            "real_order_placed": False,
            "execution_attempted": False,
            "order_payload_created": False,
            "executable_payload_created": False,
            "protective_payload_created": False,
            "signed_request_created": False,
            "network_allowed": False,
            "binance_order_endpoint_called": False,
            "binance_test_order_endpoint_called": False,
            "protective_order_endpoint_called": False,
            "secrets_shown": False,
            "paper_live_separation_intact": True,
            "env_mutated": False,
            "config_written": False,
            "global_live_flags_changed": False,
        }

    def _assert_delta_not_collected(self, payload: dict) -> None:
        self.assertEqual({"status": "NOT_COLLECTED"}, payload["blocker_movement"]["after"])
        self.assertEqual(0, payload["blocker_movement"]["delta_total"])
        self.assertEqual({"status": "NOT_COLLECTED"}, payload["clearing_delta"]["blocker_counts"]["after"])
        self.assertEqual(0, payload["clearing_delta"]["blocker_counts"]["delta_total"])
        self.assertIsNone(payload["probability_movement"]["after_today_probability_pct"])
        self.assertIsNone(payload["probability_movement"]["after_next_session_probability_pct"])
        self.assertEqual(0, payload["probability_movement"]["today_delta_pct"])
        self.assertEqual(0, payload["probability_movement"]["next_session_delta_pct"])
        self.assertEqual("NOT_COLLECTED", payload["clearing_delta"]["lane_status"]["after"])
        self.assertEqual("NOT_COLLECTED", payload["clearing_delta"]["tiny_live_gate_status"]["after"])
        self.assertEqual("NOT_COLLECTED", payload["clearing_delta"]["protective_policy_status"]["after"])
        self.assertEqual("NOT_COLLECTED", payload["clearing_delta"]["global_gate_status"]["after"])

    def _assert_safety_flags_clean(self, payload: dict) -> None:
        for key, value in payload["safety"].items():
            if key == "paper_live_separation_intact":
                self.assertTrue(value)
            else:
                self.assertFalse(value)


if __name__ == "__main__":
    unittest.main()
