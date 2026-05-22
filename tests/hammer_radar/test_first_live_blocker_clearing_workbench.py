from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.execution import binance_futures_connector
from src.app.hammer_radar.operator.first_live_blocker_clearing_workbench import (
    WORKBENCH_BLOCKED_UNSAFE,
    WORKBENCH_READY,
    build_first_live_blocker_clearing_workbench,
    first_live_blocker_clearing_workbench_path,
    format_first_live_blocker_clearing_workbench_text,
    load_first_live_blocker_clearing_workbenches,
)
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR


class FirstLiveBlockerClearingWorkbenchTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict(os.environ, {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False)
        self.env_patch.start()

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def _final_review(self, **overrides: object) -> dict[str, object]:
        payload: dict[str, object] = {
            "status": "FINAL_REVIEW_BLOCKED",
            "live_ready": False,
            "execution_enabled_by_final_review": False,
            "order_placed": False,
            "real_order_placed": False,
            "execution_attempted": False,
            "real_order_possible": False,
            "secrets_shown": False,
            "paper_live_separation_intact": True,
            "active_tuple": {
                "candidate_id": "candidate-1",
                "risk_contract_hash": "risk-1",
                "packet_hash": "packet-1",
                "tuple_status": "CONSISTENT",
                "source": "test",
            },
            "source_statuses": {
                "R102 final preflight": "BLOCKED",
                "R104 tiny live armed dry run": "BLOCKED_FOR_DRY_RUN",
                "R105 protocol": "PROTOCOL_BLOCKED",
                "R106 activation gate": "FIRST_LIVE_BLOCKED",
                "R109 cockpit": "COCKPIT_BLOCKED",
                "R112 evidence status": "EVIDENCE_PARTIAL",
                "R113 prerequisite recheck": "RECHECK_PARTIAL",
                "R116 assisted run latest status": "ASSISTED_RUN_PREVIEW",
                "R117 post-evidence recheck": "POST_EVIDENCE_BLOCKED",
            },
            "readiness_matrix": [
                {
                    "layer": "cockpit_sacred_button",
                    "current_status": "can_place_order=false; records_intent_only=true",
                    "satisfied": True,
                }
            ],
            "source_surfaces_used": ["R118 first-live-activation-final-review"],
        }
        payload.update(overrides)
        return payload

    def _build(self, final_review: dict[str, object] | None = None) -> dict[str, object]:
        module = "src.app.hammer_radar.operator.first_live_blocker_clearing_workbench"
        with patch(f"{module}.build_first_live_activation_final_review", return_value=final_review or self._final_review()):
            return build_first_live_blocker_clearing_workbench(candidate_id="candidate-1", log_dir=self.log_dir)

    def test_workbench_returns_required_safety_state(self) -> None:
        payload = self._build()

        self.assertEqual(WORKBENCH_READY, payload["status"])
        self.assertFalse(payload["live_ready"])
        self.assertFalse(payload["execution_enabled_by_workbench"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["execution_attempted"])
        self.assertFalse(payload["real_order_possible"])
        self.assertFalse(payload["secrets_shown"])

    def test_workbench_never_places_orders(self) -> None:
        with patch.object(binance_futures_connector, "execute_live_order") as execute_live_order:
            payload = self._build()

        execute_live_order.assert_not_called()
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["execution_attempted"])

    def test_includes_required_source_statuses(self) -> None:
        payload = self._build()

        self.assertEqual(
            {
                "R102 final preflight",
                "R104 tiny live armed dry run",
                "R105 protocol",
                "R106 activation gate",
                "R109 cockpit",
                "R112 evidence status",
                "R113 prerequisite recheck",
                "R116 assisted run",
                "R117 post-evidence recheck",
                "R118 final review",
            },
            set(payload["source_statuses"]),
        )

    def test_includes_all_required_clearing_lanes(self) -> None:
        payload = self._build()

        self.assertEqual(
            {
                "evidence_records_lane",
                "candidate_freshness_lane",
                "approval_records_lane",
                "binance_credentials_lane",
                "account_funding_read_only_lane",
                "protective_orders_lane",
                "live_adapter_boundary_lane",
                "tiny_size_max_loss_lane",
                "environment_flags_review_lane",
                "sacred_button_safety_lane",
                "final_gate_recheck_lane",
                "future_authorization_lane",
            },
            {lane["lane_id"] for lane in payload["clearing_lanes"]},
        )
        for lane in payload["clearing_lanes"]:
            self.assertIn("commands", lane)
            self.assertIn("evidence_commands", lane)
            self.assertIn("verification_commands", lane)
            self.assertIn("stop_conditions", lane)

    def test_includes_operator_sequence_assisted_commands_and_stop_conditions(self) -> None:
        payload = self._build()

        self.assertEqual(10, len(payload["immediate_operator_sequence"]))
        self.assertIn("first-live-evidence-assisted-run --all-groups", payload["assisted_evidence_commands"]["preview_all_groups"])
        self.assertEqual(
            "OPERATOR_REVIEW_REQUIRED",
            payload["assisted_evidence_commands"]["valid_execute_template"]["label"],
        )
        self.assertIn("I CONFIRM EVIDENCE RECORDING ONLY; NO LIVE ORDER; NO ENV CHANGE.", payload["assisted_evidence_commands"]["valid_execute_template"]["command"])
        self.assertIn("first-live-activation-final-review", payload["status_recheck_pack"]["first-live-activation-final-review"])
        self.assertIn("R118 does not say ready", payload["stop_conditions"])
        self.assertTrue(payload["authorization_boundary"]["R119 cannot place orders"])

    def test_blocked_unsafe_if_sacred_button_can_place_order_true(self) -> None:
        payload = self._build(
            self._final_review(
                sacred_button_state={"can_place_order": True, "records_intent_only": True},
            )
        )

        self.assertEqual(WORKBENCH_BLOCKED_UNSAFE, payload["status"])
        self.assertIn("sacred button can_place_order true", payload["unsafe_reasons"])

    def test_blocked_unsafe_if_paper_live_separation_false(self) -> None:
        payload = self._build(self._final_review(paper_live_separation_intact=False))

        self.assertEqual(WORKBENCH_BLOCKED_UNSAFE, payload["status"])
        self.assertIn("paper_live_separation_intact false", payload["unsafe_reasons"])
        self.assertFalse(payload["paper_live_separation_intact"])

    def test_blocked_unsafe_if_any_no_execution_safety_field_violates(self) -> None:
        payload = self._build(self._final_review(execution_attempted=True, real_order_possible=True))

        self.assertEqual(WORKBENCH_BLOCKED_UNSAFE, payload["status"])
        self.assertIn("execution_attempted true", payload["unsafe_reasons"])
        self.assertIn("real_order_possible true", payload["unsafe_reasons"])
        self.assertFalse(payload["execution_attempted"])
        self.assertFalse(payload["real_order_possible"])

    def test_ledger_write_contains_safety_fields(self) -> None:
        payload = self._build()
        records = load_first_live_blocker_clearing_workbenches(limit=0, log_dir=self.log_dir)

        self.assertEqual(1, len(records))
        record = records[0]
        self.assertEqual(payload["workbench_id"], record["workbench_id"])
        self.assertFalse(record["live_ready"])
        self.assertFalse(record["execution_enabled_by_workbench"])
        self.assertFalse(record["order_placed"])
        self.assertFalse(record["real_order_placed"])
        self.assertFalse(record["execution_attempted"])
        self.assertFalse(record["real_order_possible"])
        self.assertFalse(record["secrets_shown"])
        self.assertEqual(first_live_blocker_clearing_workbench_path(self.log_dir), self.log_dir / "first_live_blocker_clearing_workbench.ndjson")

    def test_paper_live_separation_remains_intact_when_sources_are_clean(self) -> None:
        payload = self._build()

        self.assertTrue(payload["paper_live_separation_intact"])

    def test_format_does_not_expose_secret_tokens(self) -> None:
        payload = self._build()
        payload["source_statuses"]["secret-api"] = "present"
        rendered = format_first_live_blocker_clearing_workbench_text(payload)

        self.assertFalse(json.loads(rendered)["secrets_shown"])

    def test_cli_outputs_json(self) -> None:
        command = [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(self.log_dir),
            "first-live-blocker-clearing-workbench",
            "--no-record",
        ]
        result = subprocess.run(command, check=True, capture_output=True, text=True, env={**os.environ, "PYTHONPATH": "."})
        payload = json.loads(result.stdout)

        self.assertIn(payload["status"], {WORKBENCH_READY, WORKBENCH_BLOCKED_UNSAFE})
        self.assertFalse(payload["live_ready"])
        self.assertFalse(payload["execution_enabled_by_workbench"])


if __name__ == "__main__":
    unittest.main()
