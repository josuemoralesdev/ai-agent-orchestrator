from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.post_clearing_live_ready_recheck import (
    AUTHORIZE_TINY_LIVE_LANE,
    CONFIRM_POST_CLEARING_RECHECK_PHRASE,
    LEDGER_FILENAME,
    RECORD_AUTONOMOUS_PAPER_PROOF,
    WAIT_FOR_FRESH_CANDIDATE,
    append_post_clearing_recheck_record,
    build_post_clearing_live_ready_recheck,
    load_post_clearing_recheck_records,
)

LANE_KEY = "BTCUSDT|13m|long|ladder_close_50_618"


class PostClearingLiveReadyRecheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.tmp.name) / "logs"
        self.now = datetime(2026, 5, 26, 12, 0, tzinfo=UTC)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_preview_writes_no_record(self) -> None:
        payload = build_post_clearing_live_ready_recheck(
            log_dir=self.log_dir,
            lane_key=LANE_KEY,
            source_statuses=self._source_statuses(routed_count=0, eligible=0),
            now=self.now,
        )

        self.assertFalse(payload["record_recheck_requested"])
        self.assertFalse(payload["recheck_recorded"])
        self.assertFalse((self.log_dir / LEDGER_FILENAME).exists())

    def test_wrong_confirmation_rejects_recording(self) -> None:
        payload = build_post_clearing_live_ready_recheck(
            log_dir=self.log_dir,
            lane_key=LANE_KEY,
            record_recheck=True,
            confirm_post_clearing_recheck="wrong",
            source_statuses=self._source_statuses(routed_count=0, eligible=0),
            now=self.now,
        )

        self.assertEqual("POST_CLEARING_RECHECK_REJECTED", payload["status"])
        self.assertTrue(payload["record_recheck_requested"])
        self.assertFalse(payload["confirmation_valid"])
        self.assertFalse(payload["recheck_recorded"])
        self.assertFalse((self.log_dir / LEDGER_FILENAME).exists())

    def test_exact_confirmation_records_recheck_only(self) -> None:
        payload = build_post_clearing_live_ready_recheck(
            log_dir=self.log_dir,
            lane_key=LANE_KEY,
            record_recheck=True,
            confirm_post_clearing_recheck=CONFIRM_POST_CLEARING_RECHECK_PHRASE,
            source_statuses=self._source_statuses(routed_count=0, eligible=0),
            now=self.now,
        )

        self.assertTrue(payload["confirmation_valid"])
        self.assertTrue(payload["recheck_recorded"])
        self.assertIsNotNone(payload["recheck_id"])
        records = load_post_clearing_recheck_records(log_dir=self.log_dir, limit=0)
        self.assertEqual(1, len(records))
        self.assertEqual(payload["recheck_id"], records[0]["recheck_id"])
        self.assertEqual(WAIT_FOR_FRESH_CANDIDATE, records[0]["next_operator_move"])

    def test_stale_or_no_candidate_waits_for_fresh_candidate(self) -> None:
        payload = build_post_clearing_live_ready_recheck(
            log_dir=self.log_dir,
            lane_key=LANE_KEY,
            source_statuses=self._source_statuses(routed_count=0, eligible=0, stale=True),
            now=self.now,
        )

        self.assertEqual(WAIT_FOR_FRESH_CANDIDATE, payload["next_operator_move"])
        self.assertFalse(payload["fresh_candidate_status"]["has_fresh_routed_candidate"])

    def test_eligible_paper_decision_records_autonomous_paper_proof_next(self) -> None:
        payload = build_post_clearing_live_ready_recheck(
            log_dir=self.log_dir,
            lane_key=LANE_KEY,
            source_statuses=self._source_statuses(routed_count=1, eligible=1, paper_records_total=0),
            now=self.now,
        )

        self.assertEqual(RECORD_AUTONOMOUS_PAPER_PROOF, payload["next_operator_move"])
        self.assertEqual(1, payload["paper_proof_status"]["paper_eligible_decisions_count"])

    def test_paper_proof_exists_but_lane_not_tiny_live_authorizes_lane_next(self) -> None:
        payload = build_post_clearing_live_ready_recheck(
            log_dir=self.log_dir,
            lane_key=LANE_KEY,
            source_statuses=self._source_statuses(
                routed_count=1,
                eligible=0,
                paper_records_total=1,
                lane_mode="armed_dry_run",
            ),
            now=self.now,
        )

        self.assertEqual(AUTHORIZE_TINY_LIVE_LANE, payload["next_operator_move"])
        self.assertTrue(payload["paper_proof_status"]["paper_proof_exists"])
        self.assertEqual("armed_dry_run", payload["lane_mode_status"]["lane_mode"])

    def test_watcher_mode_handoff_included_when_waiting_for_fresh_candidate(self) -> None:
        payload = build_post_clearing_live_ready_recheck(
            log_dir=self.log_dir,
            lane_key=LANE_KEY,
            source_statuses=self._source_statuses(routed_count=0, eligible=0),
            now=self.now,
        )

        handoff = payload["watcher_mode_handoff"]
        self.assertTrue(handoff["enabled_recommendation"])
        self.assertEqual("SAFE_WATCH_ONLY", handoff["mode"])
        self.assertIn("safe_watch_commands", handoff)

    def test_watcher_mode_handoff_is_plan_only_and_does_not_run_loop(self) -> None:
        payload = build_post_clearing_live_ready_recheck(
            log_dir=self.log_dir,
            lane_key=LANE_KEY,
            source_statuses=self._source_statuses(routed_count=0, eligible=0),
            now=self.now,
        )

        handoff = payload["watcher_mode_handoff"]
        self.assertTrue(handoff["plan_only"])
        self.assertFalse(handoff["daemon_implemented"])
        self.assertFalse(handoff["loop_started"])
        self.assertFalse(handoff["service_installed"])

    def test_command_pack_contains_only_safe_commands(self) -> None:
        payload = build_post_clearing_live_ready_recheck(
            log_dir=self.log_dir,
            lane_key=LANE_KEY,
            source_statuses=self._source_statuses(routed_count=0, eligible=0),
            now=self.now,
        )

        commands = payload["recommended_commands"]
        joined = "\n".join(commands).lower()
        self.assertTrue(any("fresh-signal-router-status" in command for command in commands))
        self.assertTrue(any("lane-autonomy-scheduler" in command for command in commands))
        self.assertTrue(any("autonomous-paper-lane-executor-integration" in command for command in commands))
        self.assertTrue(any("operator-executes-safe-clearing-pack" in command for command in commands))
        self.assertTrue(any("first-tiny-live-lane-execution-gate" in command for command in commands))
        self.assertTrue(any("first-tiny-live-autonomous-lane-authorization" in command for command in commands))
        self.assertTrue(any("autonomous-lane-live-ready-burn-down" in command for command in commands))
        self.assertTrue(any("live-ready-blocker-clearing-operator-pack" in command for command in commands))
        self.assertTrue(any("lane-control-cockpit-state" in command for command in commands))
        for forbidden in (
            "binance",
            "execute_live_order",
            "submit_test_order",
            "build_signed",
            "systemctl",
            "sudo",
            "--apply",
            "--record-",
            "--confirm-",
            "hammer_allow_live_orders=true",
            "hammer_global_kill_switch=false",
        ):
            self.assertNotIn(forbidden, joined)

    def test_probability_update_bounded_0_100(self) -> None:
        payload = build_post_clearing_live_ready_recheck(
            log_dir=self.log_dir,
            lane_key=LANE_KEY,
            source_statuses=self._source_statuses(routed_count=0, eligible=0),
            now=self.now,
        )

        update = payload["probability_update"]
        self.assertGreaterEqual(update["tiny_live_tonight_pct"], 0)
        self.assertLessEqual(update["tiny_live_tonight_pct"], 100)
        self.assertGreaterEqual(update["tiny_live_next_session_pct"], 0)
        self.assertLessEqual(update["tiny_live_next_session_pct"], 100)

    def test_safety_flags_always_false_except_paper_live_separation(self) -> None:
        payload = build_post_clearing_live_ready_recheck(
            log_dir=self.log_dir,
            lane_key=LANE_KEY,
            source_statuses=self._source_statuses(routed_count=0, eligible=0),
            now=self.now,
        )

        for key, value in payload["safety"].items():
            if key == "paper_live_separation_intact":
                self.assertTrue(value)
            else:
                self.assertFalse(value)

    def test_ledger_append_only(self) -> None:
        first = append_post_clearing_recheck_record(
            {
                "status": "POST_CLEARING_RECHECK_BLOCKED",
                "lane_key": LANE_KEY,
                "next_operator_move": WAIT_FOR_FRESH_CANDIDATE,
                "safety": self._safe(),
            },
            log_dir=self.log_dir,
        )
        second = append_post_clearing_recheck_record(
            {
                "status": "POST_CLEARING_RECHECK_BLOCKED",
                "lane_key": LANE_KEY,
                "next_operator_move": WAIT_FOR_FRESH_CANDIDATE,
                "safety": self._safe(),
            },
            log_dir=self.log_dir,
        )

        records = load_post_clearing_recheck_records(log_dir=self.log_dir, limit=0)
        self.assertEqual(2, len(records))
        self.assertEqual(first["recheck_id"], records[0]["recheck_id"])
        self.assertEqual(second["recheck_id"], records[1]["recheck_id"])

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
        )

        self.assertIn("post-clearing-live-ready-recheck", result.stdout)

    def test_no_binance_order_payload_network_env_or_config_mutation(self) -> None:
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
            payload = build_post_clearing_live_ready_recheck(
                log_dir=self.log_dir,
                lane_key=LANE_KEY,
                source_statuses=self._source_statuses(routed_count=0, eligible=0),
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
        self.assertFalse(payload["safety"]["network_allowed"])
        self.assertFalse(payload["safety"]["env_mutated"])
        self.assertFalse(payload["safety"]["config_written"])
        self.assertFalse(payload["safety"]["order_payload_created"])
        self.assertFalse(payload["safety"]["protective_payload_created"])

    def _source_statuses(
        self,
        *,
        routed_count: int,
        eligible: int,
        paper_records_total: int = 0,
        lane_mode: str = "armed_dry_run",
        stale: bool = False,
    ) -> dict[str, object]:
        return {
            "lane": {"lane_key": LANE_KEY, "mode": lane_mode},
            "lane_mode": lane_mode,
            "fresh_signal_router": {
                "status": "ROUTER_READY",
                "candidates_seen_count": routed_count + (1 if stale else 0),
                "routed_count": routed_count,
                "expired_count": 1 if stale else 0,
                "blocked_count": 0,
                "routed_candidates": [
                    {
                        "candidate_id": "candidate-1",
                        "lane_key": LANE_KEY,
                        "route_status": "ROUTED_TO_LANE",
                        "route_action": "ARMED_DRY_RUN_OBSERVE",
                    }
                ]
                if routed_count
                else [],
                "top_blockers": [{"blocker": "candidate is older than lane freshness_seconds", "count": 1}]
                if stale
                else [],
                "safety": self._safe(),
            },
            "paper_integration": {
                "status": "PAPER_EXECUTOR_INTEGRATION_PREVIEW",
                "scheduler_status": "LANE_AUTONOMY_SCHEDULER_PREVIEW",
                "paper_eligible_decisions_count": eligible,
                "paper_blocked_decisions_count": 0 if eligible else 1,
                "paper_execution_records_created": 0,
                "integration_recorded": False,
                "integration_id": None,
                "top_blockers": [{"blocker": "stale candidate only", "count": 1}] if stale else [],
                "safety": self._safe(),
            },
            "paper_integration_records_summary": {
                "records_count": paper_records_total,
                "paper_execution_records_created": paper_records_total,
                "safety": self._safe(),
            },
            "r126_tiny_live_gate": {"status": "TINY_LIVE_EXECUTION_BLOCKED", "safety": self._safe()},
            "r130_authorization": {"status": "TINY_LIVE_AUTHORIZATION_BLOCKED", "safety": self._safe()},
            "r131_kill_switch_rehearsal": {"status": "KILL_SWITCH_REHEARSAL_BLOCKED", "safety": self._safe()},
            "r132_adapter_boundary": {"status": "LIVE_ADAPTER_BOUNDARY_BLOCKED", "safety": self._safe()},
            "r134_dry_authorization": {"status": "DRY_AUTHORIZATION_BLOCKED", "safety": self._safe()},
            "r135_adapter_rehearsal": {"status": "LIVE_ADAPTER_REHEARSAL_BLOCKED", "safety": self._safe()},
            "r136_protective_policy": {"status": "PROTECTIVE_POLICY_BLOCKED", "safety": self._safe()},
            "r137_protective_preview": {"status": "PROTECTIVE_PAYLOAD_BLOCKED", "safety": self._safe()},
            "final_live_preflight": {"status": "BLOCKED", "safety": self._safe()},
            "first_live_activation_gate": {"status": "FIRST_LIVE_BLOCKED", "safety": self._safe()},
            "connector_status": {
                "api_key_present": False,
                "api_secret_present": False,
                "connector_mode": "disabled",
                "global_kill_switch": True,
                "live_execution_enabled": False,
                "allow_live_orders": False,
                "safety": self._safe(),
            },
            "binance_live_status": {"api_key_present": False, "api_secret_present": False, "safety": self._safe()},
            "protective_status": {"protective_orders_ready": False, "safety": self._safe()},
            "source_surfaces_used": ["test_source_statuses"],
        }

    def _safe(self) -> dict[str, bool]:
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
