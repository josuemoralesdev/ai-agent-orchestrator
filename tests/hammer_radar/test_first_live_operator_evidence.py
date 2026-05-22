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
    EVENT_TYPE,
    EVIDENCE_MISSING,
    EVIDENCE_PARTIAL,
    EVIDENCE_READY_FOR_PREREQ_RECHECK,
    REQUIRED_EVIDENCE_TYPES,
    build_first_live_evidence_status,
    first_live_operator_evidence_path,
    format_first_live_operator_evidence_text,
    load_first_live_operator_evidence,
    record_first_live_operator_evidence,
)
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR


class FirstLiveOperatorEvidenceTestCase(unittest.TestCase):
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
        note: str = "safe operator evidence",
    ) -> dict[str, object]:
        return record_first_live_operator_evidence(
            evidence_type=evidence_type,
            candidate_id=candidate_id,
            risk_contract_hash=risk_contract_hash,
            packet_hash=packet_hash,
            note=note,
            log_dir=self.log_dir,
        )

    def test_recording_valid_evidence_appends_ledger(self) -> None:
        first = self._record("APPROVAL_INTENT_REVIEWED")
        second = self._record("HUMAN_REVIEW_R85")
        records = load_first_live_operator_evidence(limit=0, log_dir=self.log_dir)

        self.assertTrue(first_live_operator_evidence_path(self.log_dir).exists())
        self.assertEqual(2, len(records))
        self.assertEqual({first["evidence_id"], second["evidence_id"]}, {record["evidence_id"] for record in records})
        for record in records:
            self.assertEqual(EVENT_TYPE, record["event_type"])
            self.assertTrue(record["accepted"])
            self.assertFalse(record["live_ready"])
            self.assertFalse(record["execution_enabled_by_evidence"])
            self.assertFalse(record["order_placed"])
            self.assertFalse(record["real_order_placed"])
            self.assertFalse(record["execution_attempted"])
            self.assertFalse(record["real_order_possible"])
            self.assertFalse(record["secrets_shown"])

    def test_unsupported_evidence_type_rejected(self) -> None:
        payload = self._record("BAD_TYPE")

        self.assertFalse(payload["accepted"])
        self.assertEqual("unsupported evidence_type", payload["rejection_reason"])
        self.assertFalse(payload["order_placed"])

    def test_missing_candidate_and_hash_fields_rejected(self) -> None:
        payload = record_first_live_operator_evidence(
            evidence_type="APPROVAL_INTENT_REVIEWED",
            candidate_id="",
            risk_contract_hash=None,
            packet_hash="",
            note="safe",
            log_dir=self.log_dir,
        )

        self.assertFalse(payload["accepted"])
        self.assertIn("missing candidate_id", payload["rejection_reason"])
        self.assertIn("missing risk_contract_hash", payload["rejection_reason"])
        self.assertIn("missing packet_hash", payload["rejection_reason"])
        self.assertFalse(payload["live_ready"])

    def test_missing_evidence_type_rejected(self) -> None:
        payload = record_first_live_operator_evidence(
            evidence_type=None,
            candidate_id="candidate-1",
            risk_contract_hash="risk-1",
            packet_hash="packet-1",
            note="safe",
            log_dir=self.log_dir,
        )

        self.assertFalse(payload["accepted"])
        self.assertEqual("missing evidence_type", payload["rejection_reason"])
        self.assertFalse(payload["execution_attempted"])

    def test_secret_looking_note_rejected_and_not_echoed(self) -> None:
        secret_note = "api key abc123 token password"
        payload = self._record("APPROVAL_INTENT_REVIEWED", note=secret_note)
        records = load_first_live_operator_evidence(limit=0, log_dir=self.log_dir)
        rendered = json.dumps({"payload": payload, "records": records}, sort_keys=True)

        self.assertFalse(payload["accepted"])
        self.assertIn("note appears to contain secret material", payload["rejection_reason"])
        self.assertNotIn(secret_note, rendered)
        self.assertNotIn("abc123", rendered)
        self.assertEqual("[REDACTED_SECRET_RISK]", payload["note"])
        self.assertFalse(payload["secrets_shown"])

    def test_evidence_status_returns_missing_with_no_ledger(self) -> None:
        payload = build_first_live_evidence_status(log_dir=self.log_dir)

        self.assertEqual(EVIDENCE_MISSING, payload["status"])
        self.assertEqual(0, payload["records_count"])
        self.assertEqual(0, payload["accepted_records_count"])
        self.assertEqual(0, payload["rejected_records_count"])
        self.assertEqual(list(REQUIRED_EVIDENCE_TYPES), payload["required_evidence_types"])
        self.assertFalse(payload["live_ready"])

    def test_evidence_status_returns_partial_with_incomplete_records(self) -> None:
        self._record("APPROVAL_INTENT_REVIEWED")

        payload = build_first_live_evidence_status(log_dir=self.log_dir)

        self.assertEqual(EVIDENCE_PARTIAL, payload["status"])
        self.assertEqual(["APPROVAL_INTENT_REVIEWED"], payload["evidence_types_present"])
        self.assertIn("HUMAN_REVIEW_R85", payload["evidence_types_missing"])
        self.assertFalse(payload["execution_enabled_by_evidence"])

    def test_evidence_status_ready_when_all_required_accepted_for_consistent_tuple(self) -> None:
        for evidence_type in REQUIRED_EVIDENCE_TYPES:
            self._record(evidence_type)

        payload = build_first_live_evidence_status(log_dir=self.log_dir)

        self.assertEqual(EVIDENCE_READY_FOR_PREREQ_RECHECK, payload["status"])
        self.assertEqual([], payload["evidence_types_missing"])
        self.assertEqual(["candidate-1"], payload["candidate_ids_seen"])
        self.assertEqual(["risk-1"], payload["risk_contract_hashes_seen"])
        self.assertEqual(["packet-1"], payload["packet_hashes_seen"])
        self.assertEqual("candidate-1", payload["ready_tuple"]["candidate_id"])
        self.assertFalse(payload["order_placed"])

    def test_mixed_candidate_or_hash_tuples_do_not_return_ready(self) -> None:
        for index, evidence_type in enumerate(REQUIRED_EVIDENCE_TYPES):
            self._record(
                evidence_type,
                candidate_id=f"candidate-{index % 2}",
                risk_contract_hash="risk-1",
                packet_hash="packet-1",
            )

        payload = build_first_live_evidence_status(log_dir=self.log_dir)

        self.assertEqual(EVIDENCE_PARTIAL, payload["status"])
        self.assertIsNone(payload["ready_tuple"])
        self.assertGreater(len(payload["candidate_ids_seen"]), 1)

    def test_evidence_commands_never_place_orders_or_attempt_execution(self) -> None:
        with patch.object(binance_futures_connector, "execute_live_order") as execute_live_order:
            record = self._record("APPROVAL_INTENT_REVIEWED")
            status = build_first_live_evidence_status(log_dir=self.log_dir)

        execute_live_order.assert_not_called()
        for payload in (record, status):
            self.assertFalse(payload["live_ready"])
            self.assertFalse(payload["order_placed"])
            self.assertFalse(payload["real_order_placed"])
            self.assertFalse(payload["execution_attempted"])
            self.assertFalse(payload["real_order_possible"])
            self.assertFalse(payload["secrets_shown"])

    def test_paper_live_separation_remains_intact_and_formatter_returns_json(self) -> None:
        payload = self._record("SACRED_BUTTON_INTENT_ONLY_VERIFIED")
        rendered = format_first_live_operator_evidence_text(payload)
        parsed = json.loads(rendered)

        self.assertFalse(parsed["live_ready"])
        self.assertFalse(parsed["execution_enabled_by_evidence"])
        self.assertFalse(parsed["order_placed"])
        self.assertIn("R106 remains first-live activation authority.", parsed["safety_notes"])
        self.assertIn("R109 sacred button remains intent-only.", parsed["safety_notes"])

    def test_inspect_cli_record_and_status_output_json(self) -> None:
        record_result = subprocess.run(
            [
                ".venv/bin/python",
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                str(self.log_dir),
                "record-first-live-evidence",
                "--evidence-type",
                "APPROVAL_INTENT_REVIEWED",
                "--candidate-id",
                "candidate-1",
                "--risk-contract-hash",
                "risk-1",
                "--packet-hash",
                "packet-1",
                "--note",
                "safe cli note",
            ],
            cwd=Path(__file__).resolve().parents[2],
            check=True,
            capture_output=True,
            text=True,
        )
        record_payload = json.loads(record_result.stdout)
        self.assertTrue(record_payload["accepted"])
        self.assertFalse(record_payload["order_placed"])

        status_result = subprocess.run(
            [
                ".venv/bin/python",
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                str(self.log_dir),
                "first-live-evidence-status",
            ],
            cwd=Path(__file__).resolve().parents[2],
            check=True,
            capture_output=True,
            text=True,
        )
        status_payload = json.loads(status_result.stdout)
        self.assertEqual(EVIDENCE_PARTIAL, status_payload["status"])
        self.assertFalse(status_payload["execution_enabled_by_evidence"])


if __name__ == "__main__":
    unittest.main()
