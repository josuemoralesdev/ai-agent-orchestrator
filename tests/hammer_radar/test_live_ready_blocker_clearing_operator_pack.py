from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.live_ready_blocker_clearing_operator_pack import (
    BLOCKER_CLEARING_PACK_READY,
    BLOCKER_CLEARING_PACK_REJECTED,
    CONFIRM_OPERATOR_PACK_RECORDING_PHRASE,
    EVENT_TYPE,
    LEDGER_FILENAME,
    append_blocker_clearing_operator_pack_record,
    build_live_ready_blocker_clearing_operator_pack,
    load_blocker_clearing_operator_pack_records,
)

LANE_KEY = "BTCUSDT|13m|long|ladder_close_50_618"


class LiveReadyBlockerClearingOperatorPackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.tmp.name) / "logs"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_preview_writes_no_pack_record(self) -> None:
        payload = self._pack()

        self.assertEqual(BLOCKER_CLEARING_PACK_READY, payload["status"])
        self.assertFalse(payload["record_pack_requested"])
        self.assertFalse(payload["pack_recorded"])
        self.assertFalse((self.log_dir / LEDGER_FILENAME).exists())

    def test_wrong_confirmation_rejects_recording(self) -> None:
        payload = self._pack(record_pack=True, confirm_operator_pack="wrong")

        self.assertEqual(BLOCKER_CLEARING_PACK_REJECTED, payload["status"])
        self.assertTrue(payload["record_pack_requested"])
        self.assertFalse(payload["confirmation_valid"])
        self.assertFalse(payload["pack_recorded"])
        self.assertFalse((self.log_dir / LEDGER_FILENAME).exists())

    def test_exact_confirmation_records_pack_only(self) -> None:
        payload = self._pack(
            record_pack=True,
            confirm_operator_pack=CONFIRM_OPERATOR_PACK_RECORDING_PHRASE,
        )
        records = load_blocker_clearing_operator_pack_records(log_dir=self.log_dir, limit=0)

        self.assertEqual(BLOCKER_CLEARING_PACK_READY, payload["status"])
        self.assertTrue(payload["confirmation_valid"])
        self.assertTrue(payload["pack_recorded"])
        self.assertEqual(1, len(records))
        self.assertEqual(EVENT_TYPE, records[0]["event_type"])
        self.assertEqual(LANE_KEY, records[0]["lane_key"])
        self.assertFalse(records[0]["safety"]["order_placed"])
        self.assertFalse(records[0]["safety"]["execution_attempted"])
        self.assertFalse(records[0]["safety"]["network_allowed"])

    def test_stages_include_all_required_stage_titles(self) -> None:
        titles = [stage["title"] for stage in self._pack()["stages"]]

        self.assertEqual(
            [
                "Visibility and current truth",
                "Paper proof",
                "Lane tiny_live intent",
                "Tiny-live gate recheck",
                "Protective readiness",
                "Credentials and adapter boundary",
                "Global gates",
                "Dry authorization readiness",
                "Future explicit live authorization",
            ],
            titles,
        )

    def test_next_three_actions_contains_max_three_actions(self) -> None:
        actions = self._pack()["next_three_actions"]

        self.assertLessEqual(len(actions), 3)
        self.assertEqual([1, 2, 3], [item["rank"] for item in actions])
        self.assertEqual("R138 burn-down", actions[0]["action"])
        self.assertEqual("Preview R129 paper executor integration", actions[1]["action"])
        self.assertEqual("Record R129 paper proof template", actions[2]["action"])

    def test_commands_are_classified(self) -> None:
        payload = self._pack()
        allowed = {
            "SAFE_READ_ONLY",
            "SAFE_PREVIEW",
            "SAFE_RECORD_EVIDENCE_WITH_CONFIRMATION",
            "FUTURE_EXPLICIT_APPLY_ONLY",
            "FUTURE_PHASE_ONLY",
            "FORBIDDEN",
        }

        for stage in payload["stages"]:
            self.assertGreater(len(stage["commands"]), 0)
            for command in stage["commands"]:
                self.assertIn(command["command_type"], allowed)
                self.assertIn("do_not_run_now", command)

    def test_forbidden_commands_are_not_included_as_runnable_actions(self) -> None:
        payload = self._pack()

        for stage in payload["stages"]:
            for command in stage["commands"]:
                if command["command_type"] in {"FUTURE_EXPLICIT_APPLY_ONLY", "FUTURE_PHASE_ONLY", "FORBIDDEN"}:
                    self.assertTrue(command["do_not_run_now"])
        for action in payload["next_three_actions"]:
            self.assertNotIn(action["command_type"], {"FUTURE_EXPLICIT_APPLY_ONLY", "FUTURE_PHASE_ONLY", "FORBIDDEN"})

    def test_command_pack_contains_no_binance_order_env_mutation_or_unsafe_apply_commands(self) -> None:
        rendered = json.dumps(self._pack())
        forbidden = (
            "execute_live_order",
            "live-connector-submit",
            "submit_test_order",
            "submit_protective_test",
            "/fapi/v1/order",
            "BINANCE_API_KEY=",
            "BINANCE_API_SECRET=",
            "export ",
            "sed -i",
            "--apply ",
            "--apply-lane-mode-change",
            "sudo",
            "systemctl",
        )
        for token in forbidden:
            self.assertNotIn(token, rendered)

    def test_probability_ladder_included_and_bounded(self) -> None:
        ladder = self._pack()["probability_ladder"]

        self.assertEqual(9, len(ladder))
        for step in ladder:
            self.assertGreaterEqual(step["probability_pct"], 0)
            self.assertLessEqual(step["probability_pct"], 100)

    def test_safety_flags_are_always_false_and_separation_true(self) -> None:
        safety = self._pack()["safety"]

        for key, value in safety.items():
            if key == "paper_live_separation_intact":
                self.assertTrue(value)
            else:
                self.assertFalse(value)

    def test_ledger_append_only(self) -> None:
        first = self._pack()
        second = self._pack()
        append_blocker_clearing_operator_pack_record(first, log_dir=self.log_dir)
        append_blocker_clearing_operator_pack_record(second, log_dir=self.log_dir)
        records = load_blocker_clearing_operator_pack_records(log_dir=self.log_dir, limit=0)

        self.assertEqual(2, len(records))
        self.assertNotEqual(records[0]["pack_id"], records[1]["pack_id"])

    def test_cli_mode_exists_and_returns_compact_status(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                str(self.log_dir),
                "live-ready-blocker-clearing-operator-pack",
                "--lane-key",
                LANE_KEY,
            ],
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": "."},
        )

        payload = json.loads(result.stdout)
        self.assertIn(payload["status"], {BLOCKER_CLEARING_PACK_READY, "BLOCKER_CLEARING_PACK_BLOCKED", "BLOCKER_CLEARING_PACK_ERROR"})
        self.assertIn("next_three_actions", payload)
        self.assertIn("stages", payload)
        self.assertLess(len(result.stdout), 160000)

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
            self._pack()

        execute_live_order.assert_not_called()
        preview_payload.assert_not_called()
        protective_preview.assert_not_called()
        submit_test_order.assert_not_called()
        submit_protective_test.assert_not_called()
        build_signed_live_order_request.assert_not_called()
        build_signed_test_order_request.assert_not_called()
        build_signed_protective_order_requests.assert_not_called()

    def _pack(self, **kwargs: object) -> dict:
        return build_live_ready_blocker_clearing_operator_pack(
            log_dir=self.log_dir,
            lane_key=LANE_KEY,
            source_statuses=self._source_statuses(),
            **kwargs,
        )

    @staticmethod
    def _source_statuses() -> dict:
        safety = {
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
        return {
            "lane": {"lane_key": LANE_KEY, "mode": "armed_dry_run", "require_protective_orders": True},
            "lane_mode": "armed_dry_run",
            "fresh_signal_router": {"status": "FRESH_SIGNAL_ROUTER_READY", "routed_count": 0, "routed_candidates": []},
            "paper_integration": {"status": "PAPER_EXECUTOR_INTEGRATION_PREVIEW", "recorded_count": 0, "top_blockers": []},
            "paper_integration_records_summary": {"recorded_count": 0, "latest_status": "MISSING"},
            "r126_tiny_live_gate": {
                "status": "TINY_LIVE_EXECUTION_BLOCKED",
                "lane_mode": "armed_dry_run",
                "paper_proof": {"matched": False, "blockers": ["no recent R125/R129 autonomous paper proof for lane"]},
                "blockers": ["lane mode is not tiny_live: armed_dry_run"],
                "safety": safety,
            },
            "r130_authorization": {
                "status": "TINY_LIVE_AUTHORIZATION_BLOCKED",
                "blockers": ["recent autonomous paper proof is missing"],
                "safety": safety,
            },
            "r130_authorization_records_summary": {"recorded_count": 0, "latest_status": "MISSING"},
            "r131_kill_switch_rehearsal": {"status": "KILL_SWITCH_REHEARSAL_BLOCKED", "current_blockers": [], "safety": safety},
            "r132_adapter_boundary": {"status": "LIVE_ADAPTER_BOUNDARY_BLOCKED", "main_blockers": ["live order adapter not configured"], "safety": safety},
            "r134_dry_authorization": {"status": "DRY_AUTHORIZATION_BLOCKED", "blockers": ["R130 tiny-live authorization is missing or blocked"], "safety": safety},
            "r135_adapter_rehearsal": {"status": "LIVE_ADAPTER_REHEARSAL_BLOCKED", "main_blockers": ["R134 blocked"], "safety": safety},
            "r136_protective_policy": {"status": "PROTECTIVE_POLICY_BLOCKED", "main_blockers": ["stop policy not ready"], "safety": safety},
            "r137_protective_preview": {"status": "PROTECTIVE_PAYLOAD_BLOCKED", "main_blockers": ["latest R136 ready policy record is missing"], "safety": safety},
            "final_live_preflight": {"status": "BLOCKED", "blockers": ["live execution disabled"], "safety": safety},
            "first_live_activation_gate": {"status": "FIRST_LIVE_BLOCKED", "blockers": ["Binance credentials missing"], "safety": safety},
            "live_env_boundary": {"boundary_status": "LIVE_ENV_ARMING_NOT_ALLOWED_YET", "blockers": ["live env boundary recheck required"], "safety": safety},
            "live_arming_preflight": {"final_preflight_status": "BLOCKED_BY_LIVE_ENV_LOCKS", "blockers": ["live arming preflight recheck required"], "safety": safety},
            "risk_contract": {"validation": {"validation_status": "RISK_CONTRACT_VALID_FOR_PREFLIGHT"}},
            "binance_live_status": {"api_key_present": False, "api_secret_present": False, "readiness": "BLOCKED"},
            "connector_status": {
                "connector_mode": "DRY_RUN_ONLY",
                "api_key_present": False,
                "api_secret_present": False,
                "global_kill_switch": True,
                "live_execution_enabled": False,
                "allow_live_orders": False,
                "live_order_adapter_configured": False,
                "safety": safety,
            },
            "protective_status": {
                "protective_orders_enabled": False,
                "protective_order_mode": "PREVIEW_ONLY",
                "protective_stop_supported": False,
                "protective_take_profit_supported": False,
                "protective_orders_ready": False,
                "blockers": [],
            },
            "source_surfaces_used": ["test_fixture"],
        }


if __name__ == "__main__":
    unittest.main()
