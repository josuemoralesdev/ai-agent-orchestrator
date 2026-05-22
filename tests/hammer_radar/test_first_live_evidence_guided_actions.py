from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.execution import binance_futures_connector
from src.app.hammer_radar.operator.first_live_evidence_guided_actions import (
    ACTIONS_BLOCKED_NO_ACTIVE_TUPLE,
    ACTIONS_READY,
    EVENT_TYPE,
    GROUP_ORDER,
    build_first_live_evidence_guided_actions,
    first_live_evidence_guided_actions_path,
    format_first_live_evidence_guided_actions_text,
    load_first_live_evidence_guided_actions,
)
from src.app.hammer_radar.operator.first_live_operator_evidence import (
    REQUIRED_EVIDENCE_TYPES,
    record_first_live_operator_evidence,
)
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR


class FirstLiveEvidenceGuidedActionsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict(os.environ, {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False)
        self.env_patch.start()

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def _payload(self, *, record: bool = True, env: dict[str, str] | None = None) -> dict[str, object]:
        return build_first_live_evidence_guided_actions(
            candidate_id="candidate-1",
            log_dir=self.log_dir,
            env={} if env is None else env,
            record=record,
        )

    def _record(self, evidence_type: str, payload: dict[str, object]) -> None:
        active_tuple = payload["active_tuple"]
        assert isinstance(active_tuple, dict)
        record_first_live_operator_evidence(
            evidence_type=evidence_type,
            candidate_id=str(active_tuple["candidate_id"]),
            risk_contract_hash=str(active_tuple["risk_contract_hash"]),
            packet_hash=str(active_tuple["packet_hash"]),
            note="safe operator evidence",
            log_dir=self.log_dir,
        )

    @contextmanager
    def _source_payloads(
        self,
        *,
        recheck_extra: dict[str, object] | None = None,
        activation_gate_extra: dict[str, object] | None = None,
    ) -> object:
        tuple_payload = {
            "candidate_id": "candidate-1",
            "risk_contract_hash": "risk-hash",
            "packet_hash": "packet-hash",
        }
        recheck = {
            "status": "RECHECK_BLOCKED",
            "recheck_tuple": dict(tuple_payload),
            "source_statuses": {},
            "source_surfaces_used": [],
            "blocker_recheck": [],
        }
        activation_gate = {
            "status": "FIRST_LIVE_BLOCKED",
            **tuple_payload,
        }
        if recheck_extra:
            recheck.update(recheck_extra)
        if activation_gate_extra:
            activation_gate.update(activation_gate_extra)
        with (
            patch(
                "src.app.hammer_radar.operator.first_live_evidence_guided_actions.build_first_live_evidence_status",
                return_value={
                    "status": "EVIDENCE_MISSING",
                    "ready_tuple": dict(tuple_payload),
                    "evidence_types_missing": list(REQUIRED_EVIDENCE_TYPES),
                },
            ),
            patch(
                "src.app.hammer_radar.operator.first_live_evidence_guided_actions.build_first_live_prerequisite_recheck_after_evidence",
                return_value=recheck,
            ),
            patch(
                "src.app.hammer_radar.operator.first_live_evidence_guided_actions.build_first_live_activation_gate",
                return_value=activation_gate,
            ),
        ):
            yield

    def test_guided_actions_returns_required_safety_state(self) -> None:
        payload = self._payload()

        self.assertEqual(ACTIONS_READY, payload["status"])
        self.assertFalse(payload["live_ready"])
        self.assertFalse(payload["execution_enabled_by_guided_actions"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["execution_attempted"])
        self.assertFalse(payload["real_order_possible"])
        self.assertFalse(payload["secrets_shown"])

    def test_missing_nested_paper_live_separation_does_not_force_false(self) -> None:
        with self._source_payloads():
            payload = self._payload(record=False)

        self.assertTrue(payload["paper_live_separation_intact"])
        self.assertEqual([], payload["warnings"])

    def test_explicit_false_paper_live_separation_from_source_is_preserved(self) -> None:
        with self._source_payloads(recheck_extra={"paper_live_separation_intact": False}):
            payload = self._payload(record=False)

        self.assertFalse(payload["paper_live_separation_intact"])

    def test_explicit_false_paper_live_separation_adds_source_warning(self) -> None:
        with self._source_payloads(activation_gate_extra={"paper_live_separation_intact": False}):
            payload = self._payload(record=False)

        self.assertFalse(payload["paper_live_separation_intact"])
        self.assertEqual(
            ["paper_live_separation_intact explicitly false from source(s): R106 activation gate"],
            payload["warnings"],
        )

    def test_normal_guided_actions_output_has_paper_live_separation_intact(self) -> None:
        payload = self._payload(record=False)

        self.assertTrue(payload["paper_live_separation_intact"])

    def test_guided_actions_never_places_orders_or_attempts_execution(self) -> None:
        with patch.object(binance_futures_connector, "execute_live_order") as execute_live_order:
            payload = self._payload()

        execute_live_order.assert_not_called()
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["execution_attempted"])
        self.assertFalse(payload["real_order_possible"])

    def test_guided_actions_does_not_expose_secret_values_from_env(self) -> None:
        env = {
            "BINANCE_API_KEY": "secret-api-key-value",
            "BINANCE_API_SECRET": "secret-api-secret-value",
            "TELEGRAM_BOT_TOKEN": "secret-telegram-token",
            "TELEGRAM_CHAT_ID": "secret-chat-id",
        }

        payload = self._payload(env=env)
        rendered = json.dumps(payload, sort_keys=True)

        self.assertNotIn("secret-api-key-value", rendered)
        self.assertNotIn("secret-api-secret-value", rendered)
        self.assertNotIn("secret-telegram-token", rendered)
        self.assertNotIn("secret-chat-id", rendered)
        self.assertFalse(payload["secrets_shown"])

    def test_guided_actions_includes_active_tuple_and_missing_evidence_types(self) -> None:
        payload = self._payload()
        active_tuple = payload["active_tuple"]

        self.assertIsInstance(active_tuple, dict)
        self.assertEqual("PRESENT", active_tuple["tuple_status"])
        self.assertEqual("candidate-1", active_tuple["candidate_id"])
        self.assertTrue(active_tuple["risk_contract_hash"])
        self.assertTrue(active_tuple["packet_hash"])
        self.assertEqual(list(REQUIRED_EVIDENCE_TYPES), payload["missing_evidence_types"])

    def test_guided_actions_generates_record_commands_for_missing_types(self) -> None:
        payload = self._payload()
        active_tuple = payload["active_tuple"]
        commands = payload["evidence_recording_commands"]

        self.assertEqual(len(REQUIRED_EVIDENCE_TYPES), len(commands))
        self.assertEqual(list(REQUIRED_EVIDENCE_TYPES), [item["evidence_type"] for item in commands])
        for item in commands:
            command = item["command"]
            self.assertIn("record-first-live-evidence", command)
            self.assertIn("--evidence-type", command)
            self.assertIn("--candidate-id candidate-1", command)
            self.assertIn(f"--risk-contract-hash {active_tuple['risk_contract_hash']}", command)
            self.assertIn(f"--packet-hash {active_tuple['packet_hash']}", command)
            self.assertIn("--note", command)
            self.assertNotIn("execute", command)
            self.assertNotIn("submit", command)
            self.assertNotIn("binance", command.lower())

    def test_generated_command_notes_do_not_include_secret_like_content(self) -> None:
        payload = self._payload()
        pattern = re.compile(r"--note (?P<note>'.*?'|\\S+)$")

        for item in payload["evidence_recording_commands"]:
            match = pattern.search(item["command"])
            self.assertIsNotNone(match)
            note = match.group("note").strip("'")
            lowered = note.lower()
            self.assertNotIn("api key", lowered)
            self.assertNotIn("api_secret", lowered)
            self.assertNotIn("secret", lowered)
            self.assertNotIn("token", lowered)
            self.assertNotIn("password", lowered)

    def test_complete_current_tuple_evidence_produces_recheck_only_pack(self) -> None:
        first_payload = self._payload(record=False)
        for evidence_type in REQUIRED_EVIDENCE_TYPES:
            self._record(evidence_type, first_payload)

        payload = self._payload(record=False)

        if payload["active_tuple"]["tuple_status"] == "PRESENT":
            self.assertEqual([], payload["missing_evidence_types"])
            self.assertEqual([], payload["evidence_recording_commands"])
        else:
            self.assertEqual(ACTIONS_BLOCKED_NO_ACTIVE_TUPLE, payload["status"])
            self.assertEqual([], payload["evidence_recording_commands"])
        self.assertTrue(payload["recheck_commands"])

    def test_grouped_actions_contains_required_categories(self) -> None:
        payload = self._payload()

        self.assertEqual(GROUP_ORDER, list(payload["grouped_actions"].keys()))
        self.assertTrue(payload["grouped_actions"]["approval_records"])
        self.assertTrue(payload["grouped_actions"]["account_funding"])
        self.assertTrue(payload["grouped_actions"]["protective_orders"])
        self.assertTrue(payload["grouped_actions"]["adapter_boundary"])
        self.assertTrue(payload["grouped_actions"]["risk_limits"])
        self.assertTrue(payload["grouped_actions"]["environment"])
        self.assertTrue(payload["grouped_actions"]["sacred_button"])
        self.assertTrue(payload["grouped_actions"]["emergency"])
        self.assertTrue(payload["grouped_actions"]["position_conflict"])

    def test_recheck_commands_include_required_sequence(self) -> None:
        payload = self._payload()
        commands = payload["recheck_commands"]

        self.assertEqual(6, len(commands))
        self.assertIn("first-live-evidence-status", commands[0])
        self.assertIn("first-live-prerequisite-recheck-after-evidence", commands[1])
        self.assertIn("first-live-prerequisite-clearing", commands[2])
        self.assertIn("first-live-burn-down", commands[3])
        self.assertIn("first-live-activation-gate", commands[4])
        self.assertIn("/operator/approval-cockpit/state", commands[5])

    def test_missing_active_tuple_returns_blocked_no_active_tuple(self) -> None:
        with (
            patch(
                "src.app.hammer_radar.operator.first_live_evidence_guided_actions.build_first_live_evidence_status",
                return_value={"status": "EVIDENCE_MISSING", "evidence_types_missing": list(REQUIRED_EVIDENCE_TYPES), "ready_tuple": None},
            ),
            patch(
                "src.app.hammer_radar.operator.first_live_evidence_guided_actions.build_first_live_prerequisite_recheck_after_evidence",
                return_value={"status": "RECHECK_BLOCKED", "recheck_tuple": None, "source_surfaces_used": [], "paper_live_separation_intact": True},
            ),
            patch(
                "src.app.hammer_radar.operator.first_live_evidence_guided_actions.build_first_live_activation_gate",
                return_value={"status": "FIRST_LIVE_BLOCKED", "paper_live_separation_intact": True},
            ),
        ):
            payload = self._payload()

        self.assertEqual(ACTIONS_BLOCKED_NO_ACTIVE_TUPLE, payload["status"])
        self.assertEqual("MISSING", payload["active_tuple"]["tuple_status"])
        self.assertEqual([], payload["evidence_recording_commands"])
        self.assertFalse(payload["live_ready"])

    def test_ledger_write_contains_required_safety_fields(self) -> None:
        payload = self._payload()
        records = load_first_live_evidence_guided_actions(limit=0, log_dir=self.log_dir)

        self.assertTrue(first_live_evidence_guided_actions_path(self.log_dir).exists())
        self.assertEqual(1, len(records))
        record = records[0]
        self.assertEqual(EVENT_TYPE, record["event_type"])
        self.assertEqual(payload["action_pack_id"], record["action_pack_id"])
        self.assertEqual(payload["active_tuple"], record["active_tuple"])
        self.assertEqual(payload["missing_evidence_types"], record["missing_evidence_types"])
        self.assertEqual(len(payload["evidence_recording_commands"]), record["evidence_recording_commands_count"])
        self.assertIn("grouped_actions", record)
        self.assertFalse(record["live_ready"])
        self.assertFalse(record["execution_enabled_by_guided_actions"])
        self.assertFalse(record["order_placed"])
        self.assertFalse(record["real_order_placed"])
        self.assertFalse(record["execution_attempted"])
        self.assertFalse(record["real_order_possible"])
        self.assertFalse(record["secrets_shown"])

    def test_paper_live_separation_remains_intact_and_formatter_returns_json(self) -> None:
        payload = self._payload(record=False)
        rendered = format_first_live_evidence_guided_actions_text(payload)
        parsed = json.loads(rendered)

        self.assertTrue(parsed["paper_live_separation_intact"])
        self.assertFalse(parsed["live_ready"])
        self.assertFalse(parsed["execution_enabled_by_guided_actions"])
        self.assertTrue(parsed["safety_summary"]["R106 remains authority"])
        self.assertTrue(parsed["safety_summary"]["R109 sacred button remains intent-only"])

    def test_inspect_cli_guided_actions_output_json(self) -> None:
        result = subprocess.run(
            [
                ".venv/bin/python",
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                str(self.log_dir),
                "first-live-evidence-guided-actions",
                "--candidate-id",
                "candidate-1",
            ],
            cwd=Path(__file__).resolve().parents[2],
            check=True,
            capture_output=True,
            text=True,
        )

        payload = json.loads(result.stdout)
        self.assertEqual(ACTIONS_READY, payload["status"])
        self.assertFalse(payload["live_ready"])
        self.assertFalse(payload["execution_enabled_by_guided_actions"])
        self.assertTrue(payload["evidence_recording_commands"])


if __name__ == "__main__":
    unittest.main()
