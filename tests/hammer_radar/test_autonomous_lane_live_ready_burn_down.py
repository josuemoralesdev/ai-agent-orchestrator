from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.autonomous_lane_live_ready_burn_down import (
    CONFIRM_BURN_DOWN_RECORDING_PHRASE,
    EVENT_TYPE,
    LEDGER_FILENAME,
    LIVE_READY_BURN_DOWN_READY,
    LIVE_READY_BURN_DOWN_REJECTED,
    append_live_ready_burn_down_record,
    build_autonomous_lane_live_ready_burn_down,
    build_autonomous_lane_live_ready_burn_down_cli_payload,
    build_blocker_inventory,
    build_dependency_chain,
    build_operator_burn_down_command_pack,
    build_probability_ladder,
    load_live_ready_burn_down_records,
    rank_live_ready_blockers,
)

LANE_KEY = "BTCUSDT|13m|long|ladder_close_50_618"


class AutonomousLaneLiveReadyBurnDownTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.tmp.name) / "logs"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_preview_writes_no_burn_down_record(self) -> None:
        payload = self._burn_down()

        self.assertEqual(LIVE_READY_BURN_DOWN_READY, payload["status"])
        self.assertFalse((self.log_dir / LEDGER_FILENAME).exists())
        self.assertFalse(payload["safety"]["order_placed"])

    def test_wrong_confirmation_rejects_recording(self) -> None:
        payload = build_autonomous_lane_live_ready_burn_down_cli_payload(
            log_dir=self.log_dir,
            lane_key=LANE_KEY,
            record_burn_down=True,
            confirm_burn_down="wrong",
        )

        self.assertEqual(LIVE_READY_BURN_DOWN_REJECTED, payload["status"])
        self.assertFalse(payload["confirmation_valid"])
        self.assertFalse(payload["ledger_written"])
        self.assertFalse((self.log_dir / LEDGER_FILENAME).exists())

    def test_exact_confirmation_records_burn_down_only(self) -> None:
        with patch(
            "src.app.hammer_radar.operator.autonomous_lane_live_ready_burn_down.collect_live_ready_source_statuses",
            return_value=self._source_statuses(),
        ):
            payload = build_autonomous_lane_live_ready_burn_down_cli_payload(
                log_dir=self.log_dir,
                lane_key=LANE_KEY,
                record_burn_down=True,
                confirm_burn_down=CONFIRM_BURN_DOWN_RECORDING_PHRASE,
            )
        records = load_live_ready_burn_down_records(log_dir=self.log_dir, limit=0)

        self.assertEqual(LIVE_READY_BURN_DOWN_READY, payload["status"])
        self.assertTrue(payload["ledger_written"])
        self.assertEqual(1, len(records))
        self.assertEqual(EVENT_TYPE, records[0]["event_type"])
        self.assertEqual(LANE_KEY, records[0]["lane_key"])
        self.assertFalse(records[0]["safety"]["order_placed"])
        self.assertFalse(records[0]["safety"]["real_order_placed"])
        self.assertFalse(records[0]["safety"]["execution_attempted"])
        self.assertFalse(records[0]["safety"]["order_payload_created"])
        self.assertFalse(records[0]["safety"]["executable_payload_created"])
        self.assertFalse(records[0]["safety"]["protective_payload_created"])
        self.assertFalse(records[0]["safety"]["signed_request_created"])
        self.assertFalse(records[0]["safety"]["network_allowed"])

    def test_detects_required_initial_blockers(self) -> None:
        blockers = self._burn_down()["ranked_blockers"]
        titles = {item["title"] for item in blockers}

        self.assertIn("Recent autonomous paper proof missing", titles)
        self.assertIn("Selected lane is not tiny_live", titles)
        self.assertIn("Tiny-live authorization missing or blocked", titles)
        self.assertIn("R126 tiny-live gate blocked", titles)
        self.assertIn("R106/global first-live activation gate blocked", titles)
        self.assertIn("Protective orders disabled", titles)
        self.assertIn("Protective mode PREVIEW_ONLY", titles)
        self.assertIn("Binance API key missing", titles)
        self.assertIn("Binance API secret missing", titles)
        self.assertIn("Live execution disabled", titles)
        self.assertIn("Live orders disabled", titles)
        self.assertIn("Connector mode DRY_RUN_ONLY", titles)
        self.assertIn("Live adapter not configured", titles)
        self.assertIn("Protective dry payload not ready", titles)
        self.assertIn("Order payload dry authorization blocked", titles)
        self.assertIn("Signed request forbidden until future phase", titles)
        self.assertIn("No fresh routed candidate", titles)

    def test_ranked_blockers_contain_categories_and_severities(self) -> None:
        blockers = self._burn_down()["ranked_blockers"]

        self.assertGreater(len(blockers), 0)
        for blocker in blockers:
            self.assertRegex(blocker["id"], r"^B\d{3}$")
            self.assertIn(blocker["category"], {
                "EVIDENCE",
                "LANE_MODE",
                "AUTHORIZATION",
                "PAPER_PROOF",
                "PROTECTIVE_POLICY",
                "PROTECTIVE_PAYLOAD",
                "CREDENTIAL_BOUNDARY",
                "ADAPTER_BOUNDARY",
                "GLOBAL_GATE",
                "KILL_SWITCH",
                "ENV_FLAGS",
                "RISK_CONTRACT",
                "FRESH_SIGNAL",
                "UI_VISIBILITY",
                "UNKNOWN",
            })
            self.assertIn(blocker["severity"], {"CRITICAL_BLOCKER", "HIGH_BLOCKER", "MEDIUM_BLOCKER", "LOW_BLOCKER", "INFO"})

    def test_dependency_chain_includes_paper_proof_before_live_adapter(self) -> None:
        chain = build_dependency_chain(ranked_blockers=self._burn_down()["ranked_blockers"], lane_key=LANE_KEY)
        ids = [item["id"] for item in chain]

        self.assertLess(ids.index("paper_proof"), ids.index("adapter_boundary"))

    def test_probability_ladder_included_and_bounded(self) -> None:
        ladder = build_probability_ladder(ranked_blockers=self._burn_down()["ranked_blockers"])

        self.assertGreater(len(ladder), 0)
        for step in ladder:
            self.assertGreaterEqual(step["probability_pct"], 0)
            self.assertLessEqual(step["probability_pct"], 100)

    def test_command_pack_contains_only_safe_commands(self) -> None:
        pack = build_operator_burn_down_command_pack(lane_key=LANE_KEY)
        rendered = json.dumps(pack)

        for required in (
            "lane-control-status",
            "fresh-signal-router-status",
            "autonomous-paper-lane-executor-integration",
            "first-tiny-live-autonomous-lane-authorization",
            "first-tiny-live-lane-execution-gate",
            "live-lane-kill-switch-rehearsal",
            "live-adapter-boundary-final-review",
            "protective-order-dry-policy-review",
            "protective-payload-dry-preview-boundary",
            "first-tiny-live-order-payload-dry-authorization",
            "final-live-preflight",
            "first-live-activation-gate",
        ):
            self.assertIn(required, rendered)
        forbidden = (
            "execute_live_order",
            "live-connector-submit",
            "/fapi/v1/order",
            "BINANCE_API_KEY=",
            "BINANCE_API_SECRET=",
            "export ",
            "sed -i",
            "--apply ",
            "--apply-lane-mode-change",
            "sudo",
        )
        for token in forbidden:
            self.assertNotIn(token, rendered)

    def test_safety_flags_are_always_false_and_separation_true(self) -> None:
        safety = self._burn_down()["safety"]

        for key, value in safety.items():
            if key == "paper_live_separation_intact":
                self.assertTrue(value)
            else:
                self.assertFalse(value)

    def test_ledger_append_only(self) -> None:
        first = self._burn_down()
        second = self._burn_down()
        append_live_ready_burn_down_record(first, log_dir=self.log_dir)
        append_live_ready_burn_down_record(second, log_dir=self.log_dir)
        records = load_live_ready_burn_down_records(log_dir=self.log_dir, limit=0)

        self.assertEqual(2, len(records))
        self.assertNotEqual(records[0]["burn_down_id"], records[1]["burn_down_id"])

    def test_cli_mode_exists_and_returns_compact_status(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                str(self.log_dir),
                "autonomous-lane-live-ready-burn-down",
                "--lane-key",
                LANE_KEY,
            ],
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": "."},
        )

        payload = json.loads(result.stdout)
        self.assertIn(payload["status"], {LIVE_READY_BURN_DOWN_READY, "LIVE_READY_BURN_DOWN_BLOCKED", "LIVE_READY_BURN_DOWN_ERROR"})
        self.assertIn("blocker_summary", payload)
        self.assertIn("ranked_blockers", payload)
        self.assertLess(len(result.stdout), 120000)

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
            payload = self._burn_down()

        execute_live_order.assert_not_called()
        preview_payload.assert_not_called()
        protective_preview.assert_not_called()
        submit_test_order.assert_not_called()
        submit_protective_test.assert_not_called()
        build_signed_live_order_request.assert_not_called()
        build_signed_test_order_request.assert_not_called()
        build_signed_protective_order_requests.assert_not_called()
        self.assertFalse(payload["safety"]["network_allowed"])
        self.assertFalse(payload["safety"]["signed_request_created"])

    def test_inventory_helpers_accept_source_statuses(self) -> None:
        inventory = build_blocker_inventory(source_statuses=self._source_statuses(), lane_key=LANE_KEY)
        ranked = rank_live_ready_blockers(inventory)

        self.assertGreater(len(inventory), 0)
        self.assertEqual("B001", ranked[0]["id"])

    def _burn_down(self) -> dict:
        return build_autonomous_lane_live_ready_burn_down(
            log_dir=self.log_dir,
            lane_key=LANE_KEY,
            source_statuses=self._source_statuses(),
        )

    @staticmethod
    def _source_statuses() -> dict:
        safety = {
            "order_placed": False,
            "real_order_placed": False,
            "execution_attempted": False,
            "order_payload_created": False,
            "network_allowed": False,
            "secrets_shown": False,
            "paper_live_separation_intact": True,
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
                "blockers": [
                    "lane mode is not tiny_live: armed_dry_run",
                    "R106 first-live activation gate is not FIRST_LIVE_ACTIVATION_READY",
                    "global kill switch active",
                    "live execution flags are not enabled outside R126",
                    "live order flags are not enabled outside R126",
                    "Binance credential presence is not verified",
                    "protective order readiness is false",
                    "no fresh routed candidate",
                ],
                "safety": safety,
            },
            "r130_authorization": {"status": "TINY_LIVE_AUTHORIZATION_BLOCKED", "blockers": ["recent autonomous paper proof is missing"], "safety": safety},
            "r130_authorization_records_summary": {"recorded_count": 0, "latest_status": "MISSING"},
            "r131_kill_switch_rehearsal": {"status": "KILL_SWITCH_REHEARSAL_BLOCKED", "current_blockers": ["global kill switch active"], "safety": safety},
            "r132_adapter_boundary": {"status": "LIVE_ADAPTER_BOUNDARY_BLOCKED", "main_blockers": ["live order adapter not configured"], "safety": {**safety, "binance_order_endpoint_called": False, "signed_request_created": False}},
            "r134_dry_authorization": {"status": "DRY_AUTHORIZATION_BLOCKED", "blockers": ["R130 tiny-live authorization is missing or blocked"], "safety": safety},
            "r135_adapter_rehearsal": {"status": "LIVE_ADAPTER_REHEARSAL_BLOCKED", "main_blockers": ["dry authorization missing"], "safety": safety},
            "r136_protective_policy": {"status": "PROTECTIVE_POLICY_BLOCKED", "main_blockers": ["connector_protective_boundary: protective orders are not ready"], "safety": safety},
            "r137_protective_preview": {"status": "PROTECTIVE_PAYLOAD_BLOCKED", "main_blockers": ["latest R136 ready policy record is missing"], "safety": safety},
            "final_live_preflight": {"status": "BLOCKED", "blockers": ["live execution disabled", "live orders disabled", "missing Binance credentials"], "safety": safety},
            "first_live_activation_gate": {"status": "FIRST_LIVE_BLOCKED", "blockers": ["final live preflight blocked"], "safety": safety},
            "live_env_boundary": {"boundary_status": "LIVE_ENV_ARMING_NOT_ALLOWED_YET", "blockers": ["live env locked"], "safety": safety},
            "live_arming_preflight": {"final_preflight_status": "BLOCKED_BY_LIVE_ENV_LOCKS", "blockers": ["live env locks"], "safety": safety},
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
                "blockers": ["HAMMER_PROTECTIVE_ORDERS_ENABLED is false"],
            },
            "source_surfaces_used": ["test_fixture"],
        }


if __name__ == "__main__":
    unittest.main()
