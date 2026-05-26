from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock, patch

from src.app.hammer_radar.operator.fresh_candidate_paper_proof_capture_loop import (
    CONFIRM_FRESH_CANDIDATE_WATCH_LOOP_PHRASE,
    EVENT_TYPE,
    FRESH_CANDIDATE_WATCH_CAPTURED_PAPER_PROOF,
    FRESH_CANDIDATE_WATCH_PREVIEW,
    FRESH_CANDIDATE_WATCH_REJECTED,
    FRESH_CANDIDATE_WATCH_TIMEOUT,
    LEDGER_FILENAME,
    PRIMARY_WATCHED_LANE,
    SECONDARY_WATCHED_LANE,
    append_fresh_candidate_watch_record,
    build_fresh_candidate_paper_proof_capture_loop_preview,
    build_watched_lane_specs,
    load_fresh_candidate_watch_records,
    run_fresh_candidate_paper_proof_capture_loop,
)


class FreshCandidatePaperProofCaptureLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.tmp.name) / "logs"
        self.now = datetime(2026, 5, 26, 12, 0, tzinfo=UTC)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_preview_does_not_run_loop_or_write_evidence(self) -> None:
        with (
            patch(
                "src.app.hammer_radar.operator.fresh_candidate_paper_proof_capture_loop.collect_watcher_iteration_snapshot"
            ) as collect,
            patch(
                "src.app.hammer_radar.operator.fresh_candidate_paper_proof_capture_loop.build_operator_executes_safe_clearing_pack"
            ) as r140,
        ):
            payload = build_fresh_candidate_paper_proof_capture_loop_preview(
                log_dir=self.log_dir,
                watch_all_recommended_lanes=True,
                now=self.now,
            )

        self.assertEqual(FRESH_CANDIDATE_WATCH_PREVIEW, payload["status"])
        self.assertFalse(payload["watch_started"])
        self.assertEqual(0, payload["iterations_completed"])
        self.assertFalse(payload["paper_proof_captured"])
        self.assertFalse((self.log_dir / LEDGER_FILENAME).exists())
        collect.assert_not_called()
        r140.assert_not_called()

    def test_wrong_confirmation_rejects_loop_without_sleep_or_capture(self) -> None:
        sleep_fn = Mock()
        with patch(
            "src.app.hammer_radar.operator.fresh_candidate_paper_proof_capture_loop.collect_watcher_iteration_snapshot"
        ) as collect:
            payload = run_fresh_candidate_paper_proof_capture_loop(
                log_dir=self.log_dir,
                run_watch_loop=True,
                record_watch=True,
                confirm_watch_loop="wrong",
                sleep_fn=sleep_fn,
                now=self.now,
            )

        self.assertEqual(FRESH_CANDIDATE_WATCH_REJECTED, payload["status"])
        self.assertFalse(payload["confirmation_valid"])
        self.assertFalse(payload["watch_started"])
        self.assertFalse(payload["watch_recorded"])
        self.assertFalse((self.log_dir / LEDGER_FILENAME).exists())
        collect.assert_not_called()
        sleep_fn.assert_not_called()

    def test_exact_confirmation_runs_bounded_loop_with_no_eligible_candidates(self) -> None:
        sleep_fn = Mock()
        with patch(
            "src.app.hammer_radar.operator.fresh_candidate_paper_proof_capture_loop.collect_watcher_iteration_snapshot",
            return_value=self._snapshot(routed=0, eligible=0),
        ):
            payload = run_fresh_candidate_paper_proof_capture_loop(
                log_dir=self.log_dir,
                max_iterations=2,
                sleep_seconds=10,
                run_watch_loop=True,
                confirm_watch_loop=CONFIRM_FRESH_CANDIDATE_WATCH_LOOP_PHRASE,
                sleep_fn=sleep_fn,
                now=self.now,
            )

        self.assertEqual(FRESH_CANDIDATE_WATCH_TIMEOUT, payload["status"])
        self.assertTrue(payload["watch_started"])
        self.assertTrue(payload["watch_completed"])
        self.assertEqual(2, payload["iterations_completed"])
        self.assertFalse(payload["paper_proof_captured"])
        self.assertEqual("SKIPPED_NO_ELIGIBLE_DECISION", payload["iteration_summaries"][0]["lanes"][0]["capture_status"])
        sleep_fn.assert_called_once_with(10.0)

    def test_eligible_candidate_triggers_r140_safe_path_only_and_stops_after_capture(self) -> None:
        r140_result = self._r140_capture_result()
        with (
            patch(
                "src.app.hammer_radar.operator.fresh_candidate_paper_proof_capture_loop.collect_watcher_iteration_snapshot",
                return_value=self._snapshot(routed=1, eligible=1),
            ) as collect,
            patch(
                "src.app.hammer_radar.operator.fresh_candidate_paper_proof_capture_loop.build_operator_executes_safe_clearing_pack",
                return_value=r140_result,
            ) as r140,
        ):
            payload = run_fresh_candidate_paper_proof_capture_loop(
                log_dir=self.log_dir,
                max_iterations=5,
                sleep_seconds=10,
                run_watch_loop=True,
                confirm_watch_loop=CONFIRM_FRESH_CANDIDATE_WATCH_LOOP_PHRASE,
                sleep_fn=Mock(),
                now=self.now,
            )

        self.assertEqual(FRESH_CANDIDATE_WATCH_CAPTURED_PAPER_PROOF, payload["status"])
        self.assertEqual(1, payload["iterations_completed"])
        self.assertTrue(payload["paper_proof_captured"])
        self.assertEqual(PRIMARY_WATCHED_LANE, payload["captured_lane_key"])
        self.assertEqual(["paper-1"], payload["captured_evidence_ids"])
        self.assertTrue(payload["final_lane_statuses"][PRIMARY_WATCHED_LANE]["capture_result"]["used_r140_path"])
        self.assertFalse(payload["final_lane_statuses"][PRIMARY_WATCHED_LANE]["capture_result"]["created_proof_directly_by_r142"])
        collect.assert_called_once()
        r140.assert_called_once()
        self.assertTrue(r140.call_args.kwargs["execute_safe_clearing"])
        self.assertEqual("I CONFIRM SAFE CLEARING PACK EXECUTION ONLY; NO ORDER; NO BINANCE CALL.", r140.call_args.kwargs["confirm_safe_clearing"])

    def test_supports_watching_13m_and_44m_recommended_lanes(self) -> None:
        specs = build_watched_lane_specs(watch_all_recommended_lanes=True)

        self.assertEqual([PRIMARY_WATCHED_LANE, SECONDARY_WATCHED_LANE], [spec["lane_key"] for spec in specs])
        self.assertEqual(["primary", "secondary"], [spec["role"] for spec in specs])

    def test_supports_comma_separated_lane_keys(self) -> None:
        specs = build_watched_lane_specs(lane_keys_csv=f"{PRIMARY_WATCHED_LANE},{SECONDARY_WATCHED_LANE}")

        self.assertEqual([PRIMARY_WATCHED_LANE, SECONDARY_WATCHED_LANE], [spec["lane_key"] for spec in specs])

    def test_bounds_are_enforced(self) -> None:
        payload = build_fresh_candidate_paper_proof_capture_loop_preview(
            log_dir=self.log_dir,
            max_iterations=999,
            sleep_seconds=1,
            now=self.now,
        )

        self.assertEqual(180, payload["max_iterations"])
        self.assertEqual(10, payload["sleep_seconds"])

    def test_ledger_append_only_when_record_watch_true(self) -> None:
        with patch(
            "src.app.hammer_radar.operator.fresh_candidate_paper_proof_capture_loop.collect_watcher_iteration_snapshot",
            return_value=self._snapshot(routed=0, eligible=0),
        ):
            payload = run_fresh_candidate_paper_proof_capture_loop(
                log_dir=self.log_dir,
                max_iterations=1,
                sleep_seconds=10,
                run_watch_loop=True,
                record_watch=True,
                confirm_watch_loop=CONFIRM_FRESH_CANDIDATE_WATCH_LOOP_PHRASE,
                sleep_fn=Mock(),
                now=self.now,
            )
        append_fresh_candidate_watch_record(payload, log_dir=self.log_dir)
        records = load_fresh_candidate_watch_records(log_dir=self.log_dir, limit=0)

        self.assertEqual(2, len(records))
        self.assertEqual(EVENT_TYPE, records[0]["event_type"])
        self.assertEqual(EVENT_TYPE, records[1]["event_type"])
        self.assertTrue(payload["watch_recorded"])
        self.assertEqual(payload["watch_id"], records[0]["watch_id"])

    def test_safety_flags_always_false_except_paper_live_separation(self) -> None:
        payload = build_fresh_candidate_paper_proof_capture_loop_preview(log_dir=self.log_dir, now=self.now)

        for key, value in payload["safety"].items():
            if key == "paper_live_separation_intact":
                self.assertTrue(value)
            else:
                self.assertFalse(value)

    def test_cli_exists(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--help",
            ],
            check=True,
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": "."},
        )

        self.assertIn("fresh-candidate-paper-proof-capture-loop", result.stdout)

    def test_no_binance_order_payload_network_env_or_config_mutation(self) -> None:
        from src.app.hammer_radar.execution import binance_futures_connector

        before_env = dict(os.environ)
        with (
            patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
            patch.object(binance_futures_connector, "preview_payload") as preview_payload,
            patch.object(binance_futures_connector, "protective_preview") as protective_preview,
            patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
            patch.object(binance_futures_connector, "submit_protective_test") as submit_protective_test,
            patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
            patch.object(binance_futures_connector, "build_signed_test_order_request") as build_signed_test_order_request,
            patch.object(binance_futures_connector, "build_signed_protective_order_requests") as build_signed_protective_order_requests,
            patch(
                "src.app.hammer_radar.operator.fresh_candidate_paper_proof_capture_loop.collect_watcher_iteration_snapshot",
                return_value=self._snapshot(routed=0, eligible=0),
            ),
        ):
            payload = run_fresh_candidate_paper_proof_capture_loop(
                log_dir=self.log_dir,
                max_iterations=1,
                sleep_seconds=10,
                run_watch_loop=True,
                confirm_watch_loop=CONFIRM_FRESH_CANDIDATE_WATCH_LOOP_PHRASE,
                sleep_fn=Mock(),
                now=self.now,
            )

        execute_live_order.assert_not_called()
        preview_payload.assert_not_called()
        protective_preview.assert_not_called()
        submit_test_order.assert_not_called()
        submit_protective_test.assert_not_called()
        build_signed_live_order_request.assert_not_called()
        build_signed_test_order_request.assert_not_called()
        build_signed_protective_order_requests.assert_not_called()
        self.assertEqual(before_env, dict(os.environ))
        self.assertFalse(payload["safety"]["order_payload_created"])
        self.assertFalse(payload["safety"]["executable_payload_created"])
        self.assertFalse(payload["safety"]["protective_payload_created"])
        self.assertFalse(payload["safety"]["network_allowed"])
        self.assertFalse(payload["safety"]["env_mutated"])
        self.assertFalse(payload["safety"]["config_written"])
        self.assertFalse(payload["safety"]["global_live_flags_changed"])

    def _snapshot(self, *, routed: int, eligible: int) -> dict[str, object]:
        return {
            "generated_at": self.now.isoformat(),
            "lane_key": PRIMARY_WATCHED_LANE,
            "fresh_signal_router": {
                "status": "ROUTER_READY",
                "routed_count": routed,
                "top_blockers": [] if routed else ["no fresh routed candidate"],
                "safety": self._safe(),
            },
            "lane_autonomy_scheduler": {"status": "LANE_AUTONOMY_SCHEDULER_PREVIEW", "safety": self._safe()},
            "paper_integration_preview": {
                "status": "PAPER_EXECUTOR_INTEGRATION_PREVIEW",
                "paper_eligible_decisions_count": eligible,
                "paper_blocked_decisions_count": 0 if eligible else 1,
                "top_blockers": [] if eligible else ["R129 preview reported no eligible paper decisions"],
                "safety": self._safe(),
            },
            "r141_post_clearing_recheck": {
                "status": "POST_CLEARING_RECHECK_BLOCKED",
                "next_operator_move": "RECORD_AUTONOMOUS_PAPER_PROOF" if eligible else "WAIT_FOR_FRESH_CANDIDATE",
                "safety": self._safe(),
            },
            "r138_burn_down_light_summary": {"status": "LIVE_READY_BURN_DOWN_READY", "safety": self._safe()},
            "safety": self._safe(),
            "source_surfaces_used": ["test"],
        }

    def _r140_capture_result(self) -> dict[str, object]:
        return {
            "status": "SAFE_CLEARING_EXECUTED",
            "safe_clearing_run_id": "r140-1",
            "paper_proof_result": {
                "status": "PAPER_EXECUTOR_INTEGRATION_RECORDED",
                "attempted": True,
                "used_r129_path": True,
                "paper_execution_ids": ["paper-1"],
                "integration_recorded": True,
                "integration_id": "integration-1",
                "safety": self._safe(),
            },
            "safety": self._safe(),
            "source_surfaces_used": ["R140", "R129"],
        }

    @staticmethod
    def _safe() -> dict[str, bool]:
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


if __name__ == "__main__":
    unittest.main()
