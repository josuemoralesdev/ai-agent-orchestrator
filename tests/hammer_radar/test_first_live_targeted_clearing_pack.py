from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.execution import binance_futures_connector
from src.app.hammer_radar.operator.first_live_targeted_clearing_pack import (
    AUTHORIZATION_REQUEST_NOT_READY,
    READY_TO_PREPARE_AUTHORIZATION_REQUEST,
    TARGETED_CLEARING_BLOCKED_UNSAFE,
    TARGETED_CLEARING_READY,
    build_first_live_targeted_clearing_pack,
    first_live_targeted_clearing_packs_path,
    format_first_live_targeted_clearing_pack_text,
    load_first_live_targeted_clearing_packs,
)
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR


class FirstLiveTargetedClearingPackTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict(os.environ, {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False)
        self.env_patch.start()

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def _lane(self, lane_id: str, *, current_status: str = "BLOCKED", evidence: bool = True) -> dict[str, object]:
        group = {
            "evidence_records_lane": "all-groups",
            "approval_records_lane": "approval_records",
            "account_funding_read_only_lane": "account_and_funding",
            "protective_orders_lane": "protective_orders",
            "live_adapter_boundary_lane": "adapter_boundary",
            "tiny_size_max_loss_lane": "risk_limits",
            "environment_flags_review_lane": "environment_review",
            "sacred_button_safety_lane": "sacred_button_review",
        }.get(lane_id)
        evidence_commands = []
        if evidence and group:
            evidence_commands = [
                "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward "
                f"first-live-evidence-assisted-run --group {group} --execute-evidence --confirm-evidence-only "
                '"I CONFIRM EVIDENCE RECORDING ONLY; NO LIVE ORDER; NO ENV CHANGE."'
            ]
        return {
            "lane_id": lane_id,
            "title": f"{lane_id} title",
            "owner": "OPERATOR",
            "current_status": current_status,
            "target_status": f"{lane_id} target",
            "can_clear_now": True,
            "requires_secret_handling": False,
            "requires_env_change": False,
            "requires_live_order_capability": False,
            "commands": ["preview-command"],
            "evidence_commands": evidence_commands,
            "verification_commands": ["verify-command"],
            "stop_conditions": ["active tuple changed"],
            "safety_notes": ["non-executing"],
        }

    def _workbench(self, **overrides: object) -> dict[str, object]:
        payload: dict[str, object] = {
            "status": "WORKBENCH_READY",
            "live_ready": False,
            "execution_enabled_by_workbench": False,
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
                "source": "R119 test",
            },
            "source_statuses": {
                "R112 evidence status": "EVIDENCE_PARTIAL",
                "R118 final review": "FINAL_REVIEW_BLOCKED",
            },
            "clearing_lanes": [
                self._lane("evidence_records_lane", current_status="EVIDENCE_PARTIAL"),
                self._lane("approval_records_lane"),
                self._lane("account_funding_read_only_lane"),
                self._lane("protective_orders_lane"),
                self._lane("live_adapter_boundary_lane"),
                self._lane("tiny_size_max_loss_lane"),
                self._lane("environment_flags_review_lane"),
                self._lane("sacred_button_safety_lane"),
                self._lane("candidate_freshness_lane", evidence=False),
                self._lane("final_gate_recheck_lane", evidence=False),
            ],
            "unsafe_reasons": [],
            "source_surfaces_used": ["R119 first-live-blocker-clearing-workbench", "R118 first-live-activation-final-review"],
        }
        payload.update(overrides)
        return payload

    def _build(self, workbench: dict[str, object] | None = None, **kwargs: object) -> dict[str, object]:
        module = "src.app.hammer_radar.operator.first_live_targeted_clearing_pack"
        with patch(f"{module}.build_first_live_blocker_clearing_workbench", return_value=workbench or self._workbench()):
            return build_first_live_targeted_clearing_pack(candidate_id="candidate-1", log_dir=self.log_dir, **kwargs)

    def test_targeted_clearing_returns_required_safety_state(self) -> None:
        payload = self._build()

        self.assertEqual(TARGETED_CLEARING_READY, payload["status"])
        self.assertFalse(payload["live_ready"])
        self.assertFalse(payload["execution_enabled_by_targeted_clearing"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["execution_attempted"])
        self.assertFalse(payload["real_order_possible"])
        self.assertFalse(payload["secrets_shown"])

    def test_targeted_clearing_never_places_orders(self) -> None:
        with patch.object(binance_futures_connector, "execute_live_order") as execute_live_order:
            payload = self._build()

        execute_live_order.assert_not_called()
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["execution_attempted"])

    def test_default_lane_selection_chooses_evidence_when_partial(self) -> None:
        payload = self._build()

        self.assertEqual("evidence_records_lane", payload["selected_lane"]["lane_id"])
        self.assertIn("evidence is partial or missing", payload["selected_lane"]["priority_reason"])

    def test_requested_lane_returns_that_lane_if_valid(self) -> None:
        payload = self._build(lane="sacred_button_safety_lane")

        self.assertEqual("sacred_button_safety_lane", payload["selected_lane"]["lane_id"])
        self.assertIn("sacred_button_review", payload["operator_commands"]["preview_command"])

    def test_invalid_lane_is_rejected_safely(self) -> None:
        payload = self._build(lane="unknown_lane")

        self.assertEqual(TARGETED_CLEARING_BLOCKED_UNSAFE, payload["status"])
        self.assertEqual("unknown_lane", payload["selected_lane"]["lane_id"])
        self.assertFalse(payload["live_ready"])
        self.assertFalse(payload["execution_attempted"])
        self.assertIn("invalid lane id: unknown_lane", payload["validation_errors"])

    def test_authorization_check_reports_not_ready_when_r118_blocked(self) -> None:
        payload = self._build(authorization_check=True)

        self.assertEqual(AUTHORIZATION_REQUEST_NOT_READY, payload["status"])
        self.assertEqual("AUTHORIZATION_PREP_CHECK", payload["mode_decision"]["selected_mode"])
        self.assertFalse(payload["mode_decision"]["can_request_authorization_now"])
        self.assertFalse(payload["authorization_status"]["can_prepare_authorization_request"])

    def test_ready_r118_path_returns_ready_to_prepare_authorization_but_not_live_ready(self) -> None:
        workbench = self._workbench(
            source_statuses={
                "R112 evidence status": "EVIDENCE_READY_FOR_PREREQ_RECHECK",
                "R118 final review": "READY_TO_REQUEST_FIRST_LIVE_AUTHORIZATION",
            }
        )
        payload = self._build(workbench, authorization_check=True)

        self.assertEqual(READY_TO_PREPARE_AUTHORIZATION_REQUEST, payload["status"])
        self.assertTrue(payload["authorization_status"]["can_prepare_authorization_request"])
        self.assertFalse(payload["live_ready"])
        self.assertFalse(payload["execution_enabled_by_targeted_clearing"])

    def test_stop_conditions_include_safety_blockers(self) -> None:
        payload = self._build()

        for condition in [
            "active tuple changed",
            "R118 remains blocked after evidence",
            "sacred button can_place_order true",
            "sacred button records_intent_only false",
            "paper_live_separation_intact false",
            "secrets shown",
            "order placed true",
            "execution attempted true",
            "real_order_possible true",
            "env flag change attempted",
            "Binance order endpoint appears",
            "operator has not personally verified the evidence",
            "evidence note would contain secrets",
        ]:
            self.assertIn(condition, payload["stop_conditions"])

    def test_post_clear_recheck_sequence_includes_required_phases(self) -> None:
        payload = self._build()

        self.assertEqual(
            ["R112", "R113", "R117", "R119", "R118", "R106", "R109"],
            [step["phase"] for step in payload["post_clear_recheck_sequence"]],
        )

    def test_all_evidence_lanes_includes_lane_commands(self) -> None:
        payload = self._build(all_evidence_lanes=True)

        commands = payload["all_relevant_lane_commands"]
        self.assertIn("approval_records_lane", commands)
        self.assertIn("emergency_and_position_review_lane", commands)
        self.assertIn("execute_evidence_command", commands["approval_records_lane"])

    def test_ledger_write_contains_safety_fields(self) -> None:
        payload = self._build()
        records = load_first_live_targeted_clearing_packs(limit=0, log_dir=self.log_dir)

        self.assertEqual(1, len(records))
        record = records[0]
        self.assertEqual(payload["targeted_clearing_id"], record["targeted_clearing_id"])
        self.assertFalse(record["live_ready"])
        self.assertFalse(record["execution_enabled_by_targeted_clearing"])
        self.assertFalse(record["order_placed"])
        self.assertFalse(record["real_order_placed"])
        self.assertFalse(record["execution_attempted"])
        self.assertFalse(record["real_order_possible"])
        self.assertFalse(record["secrets_shown"])
        self.assertEqual(first_live_targeted_clearing_packs_path(self.log_dir), self.log_dir / "first_live_targeted_clearing_packs.ndjson")

    def test_paper_live_separation_remains_intact(self) -> None:
        payload = self._build()

        self.assertTrue(payload["paper_live_separation_intact"])

    def test_format_does_not_expose_secret_tokens(self) -> None:
        payload = self._build()
        payload["source_surfaces_used"].append("secret-api")
        rendered = format_first_live_targeted_clearing_pack_text(payload)

        self.assertFalse(json.loads(rendered)["secrets_shown"])

    def test_cli_outputs_json(self) -> None:
        command = [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(self.log_dir),
            "first-live-targeted-clearing-pack",
            "--no-record",
        ]
        result = subprocess.run(command, check=True, capture_output=True, text=True, env={**os.environ, "PYTHONPATH": "."})
        payload = json.loads(result.stdout)

        self.assertIn(
            payload["status"],
            {
                TARGETED_CLEARING_READY,
                TARGETED_CLEARING_BLOCKED_UNSAFE,
                AUTHORIZATION_REQUEST_NOT_READY,
                READY_TO_PREPARE_AUTHORIZATION_REQUEST,
            },
        )
        self.assertFalse(payload["live_ready"])
        self.assertFalse(payload["execution_enabled_by_targeted_clearing"])


if __name__ == "__main__":
    unittest.main()
