from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.execution import binance_futures_connector
from src.app.hammer_radar.operator.first_live_operator_evidence import (
    REQUIRED_EVIDENCE_TYPES,
    record_first_live_operator_evidence,
)
from src.app.hammer_radar.operator.first_live_prerequisite_clearing import GROUP_ORDER
from src.app.hammer_radar.operator.first_live_prerequisite_recheck_after_evidence import (
    EVENT_TYPE,
    RECHECK_BLOCKED,
    RECHECK_PARTIAL,
    build_first_live_prerequisite_recheck_after_evidence,
    first_live_prerequisite_rechecks_path,
    format_first_live_prerequisite_recheck_after_evidence_text,
    load_first_live_prerequisite_rechecks,
)
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR


class FirstLivePrerequisiteRecheckAfterEvidenceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict(os.environ, {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False)
        self.env_patch.start()

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def _record(
        self,
        evidence_type: str,
        *,
        candidate_id: str = "candidate-1",
        risk_contract_hash: str = "risk-1",
        packet_hash: str = "packet-1",
    ) -> None:
        record_first_live_operator_evidence(
            evidence_type=evidence_type,
            candidate_id=candidate_id,
            risk_contract_hash=risk_contract_hash,
            packet_hash=packet_hash,
            note="safe operator evidence",
            log_dir=self.log_dir,
        )

    def test_recheck_returns_required_safety_state(self) -> None:
        payload = build_first_live_prerequisite_recheck_after_evidence(
            candidate_id="candidate-1",
            log_dir=self.log_dir,
            env={},
        )

        self.assertEqual(RECHECK_PARTIAL, payload["status"])
        self.assertFalse(payload["live_ready"])
        self.assertFalse(payload["execution_enabled_by_recheck"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["execution_attempted"])
        self.assertFalse(payload["real_order_possible"])
        self.assertFalse(payload["secrets_shown"])
        self.assertFalse(payload["sacred_button_can_place_order"])
        self.assertTrue(payload["cockpit_records_intent_only"])
        self.assertTrue(payload["r106_remains_authority"])

    def test_recheck_never_places_orders_or_attempts_execution(self) -> None:
        with patch.object(binance_futures_connector, "execute_live_order") as execute_live_order:
            payload = build_first_live_prerequisite_recheck_after_evidence(
                candidate_id="candidate-1",
                log_dir=self.log_dir,
                env={},
            )

        execute_live_order.assert_not_called()
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["execution_attempted"])
        self.assertFalse(payload["real_order_possible"])

    def test_recheck_does_not_expose_secret_values(self) -> None:
        env = {
            "BINANCE_API_KEY": "secret-api-key-value",
            "BINANCE_API_SECRET": "secret-api-secret-value",
            "TELEGRAM_BOT_TOKEN": "secret-telegram-token",
            "TELEGRAM_CHAT_ID": "secret-chat-id",
        }

        payload = build_first_live_prerequisite_recheck_after_evidence(
            candidate_id="candidate-1",
            log_dir=self.log_dir,
            env=env,
        )
        rendered = json.dumps(payload, sort_keys=True)

        self.assertNotIn("secret-api-key-value", rendered)
        self.assertNotIn("secret-api-secret-value", rendered)
        self.assertNotIn("secret-telegram-token", rendered)
        self.assertNotIn("secret-chat-id", rendered)
        self.assertFalse(payload["secrets_shown"])

    def test_source_statuses_include_r106_r109_r110_r111_and_r112(self) -> None:
        payload = build_first_live_prerequisite_recheck_after_evidence(
            candidate_id="candidate-1",
            log_dir=self.log_dir,
            env={},
        )

        self.assertEqual("FIRST_LIVE_BLOCKED", payload["source_statuses"]["R106 activation gate"])
        self.assertIn("R109 cockpit", payload["source_statuses"])
        self.assertEqual("BURN_DOWN_READY", payload["source_statuses"]["R110 burn-down"])
        self.assertEqual("PREREQS_BLOCKED", payload["source_statuses"]["R111 prerequisite clearing"])
        self.assertEqual("EVIDENCE_MISSING", payload["source_statuses"]["R112 evidence status"])

    def test_evidence_status_and_blocker_recheck_cover_required_groups(self) -> None:
        payload = build_first_live_prerequisite_recheck_after_evidence(
            candidate_id="candidate-1",
            log_dir=self.log_dir,
            env={},
        )

        self.assertEqual("EVIDENCE_MISSING", payload["evidence_status"]["status"])
        self.assertEqual(0, payload["evidence_status"]["records_count"])
        self.assertEqual(GROUP_ORDER, [item["group"] for item in payload["blocker_recheck"]])
        for item in payload["blocker_recheck"]:
            self.assertIn(item["rechecked_status"], {"CLEAR", "STILL_BLOCKED", "NEEDS_MORE_EVIDENCE", "UNKNOWN"})
            self.assertIn("previous_status", item)
            self.assertIn("evidence_present", item)
            self.assertIn("evidence_types_used", item)
            self.assertIn("blockers_remaining", item)
            self.assertIn("next_action", item)
            self.assertIn("verification_command", item)

    def test_missing_evidence_produces_needs_more_evidence_for_evidence_backed_group(self) -> None:
        payload = build_first_live_prerequisite_recheck_after_evidence(
            candidate_id="candidate-1",
            log_dir=self.log_dir,
            env={},
        )
        groups = {item["group"]: item for item in payload["blocker_recheck"]}

        self.assertEqual("NEEDS_MORE_EVIDENCE", groups["approval_records"]["rechecked_status"])
        self.assertFalse(groups["approval_records"]["evidence_present"])
        self.assertIn("approval_records", payload["evidence_needed_groups"])

    def test_complete_evidence_clears_evidence_backed_groups_without_live_readiness(self) -> None:
        for evidence_type in REQUIRED_EVIDENCE_TYPES:
            self._record(evidence_type)

        payload = build_first_live_prerequisite_recheck_after_evidence(
            candidate_id="candidate-1",
            log_dir=self.log_dir,
            env={},
        )
        groups = {item["group"]: item for item in payload["blocker_recheck"]}

        self.assertEqual(RECHECK_PARTIAL, payload["status"])
        for group in (
            "approval_records",
            "account_funding_read_only_check",
            "protective_orders_readiness",
            "live_adapter_boundary",
            "tiny_position_size_cap",
            "max_loss_cap",
            "environment_flag_review",
            "sacred_button_safety",
        ):
            self.assertEqual("CLEAR", groups[group]["rechecked_status"])
            self.assertTrue(groups[group]["evidence_present"])
            self.assertIn(group, payload["cleared_groups"])
        self.assertFalse(payload["live_ready"])
        self.assertFalse(payload["execution_enabled_by_recheck"])
        self.assertFalse(payload["real_order_possible"])

    def test_sacred_button_safety_confirms_can_place_order_false(self) -> None:
        payload = build_first_live_prerequisite_recheck_after_evidence(
            candidate_id="candidate-1",
            log_dir=self.log_dir,
            env={},
        )
        groups = {item["group"]: item for item in payload["blocker_recheck"]}

        self.assertEqual("CLEAR", groups["sacred_button_safety"]["rechecked_status"])
        self.assertFalse(payload["sacred_button_can_place_order"])
        self.assertIn("sacred_button_safety", payload["cleared_groups"])

    def test_ledger_write_contains_required_safety_fields(self) -> None:
        payload = build_first_live_prerequisite_recheck_after_evidence(
            candidate_id="candidate-1",
            log_dir=self.log_dir,
            env={},
        )
        records = load_first_live_prerequisite_rechecks(limit=0, log_dir=self.log_dir)

        self.assertTrue(first_live_prerequisite_rechecks_path(self.log_dir).exists())
        self.assertEqual(1, len(records))
        record = records[0]
        self.assertEqual(EVENT_TYPE, record["event_type"])
        self.assertEqual(payload["recheck_id"], record["recheck_id"])
        self.assertIn("source_statuses", record)
        self.assertIn("evidence_status", record)
        self.assertIn("blocker_recheck", record)
        self.assertIn("activation_distance", record)
        self.assertFalse(record["live_ready"])
        self.assertFalse(record["execution_enabled_by_recheck"])
        self.assertFalse(record["order_placed"])
        self.assertFalse(record["real_order_placed"])
        self.assertFalse(record["execution_attempted"])
        self.assertFalse(record["real_order_possible"])
        self.assertFalse(record["secrets_shown"])

    def test_paper_live_separation_remains_intact_and_formatter_returns_json(self) -> None:
        payload = build_first_live_prerequisite_recheck_after_evidence(
            candidate_id="candidate-1",
            log_dir=self.log_dir,
            env={},
        )
        rendered = format_first_live_prerequisite_recheck_after_evidence_text(payload)
        parsed = json.loads(rendered)

        self.assertTrue(parsed["paper_live_separation_intact"])
        self.assertFalse(parsed["live_ready"])
        self.assertFalse(parsed["execution_enabled_by_recheck"])

    def test_inspect_cli_recheck_output_json(self) -> None:
        result = subprocess.run(
            [
                ".venv/bin/python",
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                str(self.log_dir),
                "first-live-prerequisite-recheck-after-evidence",
                "--candidate-id",
                "candidate-1",
            ],
            cwd=Path(__file__).resolve().parents[2],
            check=True,
            capture_output=True,
            text=True,
        )

        payload = json.loads(result.stdout)
        self.assertIn(payload["status"], {RECHECK_BLOCKED, RECHECK_PARTIAL})
        self.assertFalse(payload["live_ready"])
        self.assertFalse(payload["execution_enabled_by_recheck"])
        self.assertEqual("EVIDENCE_MISSING", payload["evidence_status"]["status"])


if __name__ == "__main__":
    unittest.main()
