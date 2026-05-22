from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.execution import binance_futures_connector
from src.app.hammer_radar.operator.first_live_evidence_runbook import (
    EVENT_TYPE,
    RUNBOOK_BLOCKED,
    RUNBOOK_READY,
    STOP_CONDITIONS,
    build_first_live_evidence_runbook,
    first_live_evidence_runbooks_path,
    load_first_live_evidence_runbooks,
)
from src.app.hammer_radar.operator.first_live_operator_evidence import REQUIRED_EVIDENCE_TYPES
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR


class FirstLiveEvidenceRunbookTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict(os.environ, {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False)
        self.env_patch.start()

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def _payload(self, *, record: bool = True) -> dict[str, object]:
        return build_first_live_evidence_runbook(
            candidate_id="candidate-1",
            log_dir=self.log_dir,
            env={},
            record=record,
        )

    @contextmanager
    def _blocked_r114_payload(self) -> object:
        with patch(
            "src.app.hammer_radar.operator.first_live_evidence_runbook.build_first_live_evidence_guided_actions",
            return_value={
                "status": "ACTIONS_BLOCKED_NO_ACTIVE_TUPLE",
                "action_pack_id": "r114-pack",
                "active_tuple": {
                    "candidate_id": None,
                    "risk_contract_hash": None,
                    "packet_hash": None,
                    "tuple_status": "MISSING",
                },
                "grouped_actions": {},
                "recheck_commands": [],
                "source_surfaces_used": ["R114 first-live-evidence-guided-actions"],
                "paper_live_separation_intact": True,
                "warnings": [],
            },
        ):
            yield

    def test_runbook_returns_required_safety_state(self) -> None:
        payload = self._payload()

        self.assertEqual(RUNBOOK_READY, payload["status"])
        self.assertFalse(payload["live_ready"])
        self.assertFalse(payload["execution_enabled_by_runbook"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["execution_attempted"])
        self.assertFalse(payload["real_order_possible"])
        self.assertFalse(payload["secrets_shown"])

    def test_blocked_when_r114_has_no_active_tuple(self) -> None:
        with self._blocked_r114_payload():
            payload = self._payload(record=False)

        self.assertEqual(RUNBOOK_BLOCKED, payload["status"])
        self.assertFalse(payload["live_ready"])
        self.assertEqual("MISSING", payload["active_tuple"]["tuple_status"])

    def test_runbook_never_places_orders_or_attempts_execution(self) -> None:
        with patch.object(binance_futures_connector, "execute_live_order") as execute_live_order:
            payload = self._payload()

        execute_live_order.assert_not_called()
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["execution_attempted"])
        self.assertFalse(payload["real_order_possible"])

    def test_runbook_does_not_expose_secret_values_from_env(self) -> None:
        with patch.dict(
            os.environ,
            {
                "BINANCE_API_KEY": "secret-api-key-value",
                "BINANCE_API_SECRET": "secret-api-secret-value",
                "TELEGRAM_BOT_TOKEN": "secret-telegram-token",
            },
            clear=False,
        ):
            payload = self._payload()

        rendered = json.dumps(payload, sort_keys=True)
        self.assertNotIn("secret-api-key-value", rendered)
        self.assertNotIn("secret-api-secret-value", rendered)
        self.assertNotIn("secret-telegram-token", rendered)
        self.assertFalse(payload["secrets_shown"])

    def test_runbook_includes_active_tuple_and_all_required_sections(self) -> None:
        payload = self._payload()

        self.assertEqual(
            {"candidate_id", "risk_contract_hash", "packet_hash", "tuple_status"},
            set(payload["active_tuple"].keys()),
        )
        self.assertEqual(
            [
                "tuple_verification",
                "approval_records",
                "account_and_funding",
                "protective_orders",
                "adapter_boundary",
                "risk_limits",
                "environment_review",
                "sacred_button_review",
                "emergency_and_position_review",
                "final_recheck_sequence",
            ],
            [section["section_id"] for section in payload["runbook_sections"]],
        )
        for section in payload["runbook_sections"]:
            self.assertIn("title", section)
            self.assertIn("purpose", section)
            self.assertIn("commands", section)
            self.assertIn("verification_commands", section)
            self.assertIn("stop_conditions", section)
            self.assertIn("safety_notes", section)

    def test_runbook_includes_stop_conditions_and_operator_script_preview(self) -> None:
        payload = self._payload()

        for condition in STOP_CONDITIONS:
            self.assertIn(condition, payload["stop_conditions"])
        script = "\n".join(payload["operator_script_preview"])
        self.assertIn("set -euo pipefail", script)
        self.assertIn("REVIEW_BEFORE_RUNNING", script)
        self.assertIn("never calls Binance directly", script)
        self.assertNotIn("/api/v3/order", script)
        self.assertNotIn("/fapi/v1/order", script)
        self.assertNotIn("live-connector-submit", script)

    def test_command_pack_includes_r114_evidence_commands(self) -> None:
        payload = self._payload()
        command_pack = payload["command_pack"]
        evidence_commands = [
            command
            for command in command_pack["all_commands"]
            if "record-first-live-evidence" in command
        ]

        self.assertEqual(len(REQUIRED_EVIDENCE_TYPES), len(evidence_commands))
        for evidence_type in REQUIRED_EVIDENCE_TYPES:
            self.assertTrue(any(f"--evidence-type {evidence_type}" in command for command in evidence_commands))
        for command in command_pack["approval_record_commands"]:
            self.assertIn(command, command_pack["all_commands"])

    def test_next_recheck_sequence_includes_required_surfaces(self) -> None:
        payload = self._payload()
        sequence = payload["next_recheck_sequence"]

        self.assertEqual("first-live-evidence-status", sequence[0])
        self.assertIn("first-live-prerequisite-recheck-after-evidence", sequence)
        self.assertIn("first-live-prerequisite-clearing", sequence)
        self.assertIn("first-live-burn-down", sequence)
        self.assertIn("first-live-activation-gate", sequence)
        self.assertIn("approval cockpit state curl", sequence)

    def test_ledger_write_contains_safety_fields(self) -> None:
        payload = self._payload()
        records = load_first_live_evidence_runbooks(limit=0, log_dir=self.log_dir)

        self.assertTrue(first_live_evidence_runbooks_path(self.log_dir).exists())
        self.assertEqual(1, len(records))
        record = records[0]
        self.assertEqual(EVENT_TYPE, record["event_type"])
        self.assertEqual(payload["runbook_id"], record["runbook_id"])
        self.assertEqual(payload["active_tuple"], record["active_tuple"])
        self.assertEqual(10, record["runbook_sections_count"])
        self.assertGreater(record["command_count"], 0)
        self.assertFalse(record["live_ready"])
        self.assertFalse(record["execution_enabled_by_runbook"])
        self.assertFalse(record["order_placed"])
        self.assertFalse(record["execution_attempted"])
        self.assertFalse(record["real_order_possible"])
        self.assertFalse(record["secrets_shown"])

    def test_paper_live_separation_remains_intact(self) -> None:
        payload = self._payload(record=False)

        self.assertTrue(payload["paper_live_separation_intact"])
        self.assertTrue(payload["safety_summary"]["R106 remains authority"])
        self.assertTrue(payload["safety_summary"]["R109 sacred button remains intent-only"])

    def test_inspect_cli_runbook_output_json(self) -> None:
        result = subprocess.run(
            [
                ".venv/bin/python",
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                str(self.log_dir),
                "first-live-evidence-runbook",
                "--candidate-id",
                "candidate-1",
            ],
            cwd=Path(__file__).resolve().parents[2],
            check=True,
            capture_output=True,
            text=True,
        )

        payload = json.loads(result.stdout)
        self.assertEqual(RUNBOOK_READY, payload["status"])
        self.assertFalse(payload["live_ready"])
        self.assertFalse(payload["execution_enabled_by_runbook"])
        self.assertEqual(10, len(payload["runbook_sections"]))


if __name__ == "__main__":
    unittest.main()
