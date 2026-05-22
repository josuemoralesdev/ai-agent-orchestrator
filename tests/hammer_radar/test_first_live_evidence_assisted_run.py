from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.execution import binance_futures_connector
from src.app.hammer_radar.operator.first_live_evidence_assisted_run import (
    ASSISTED_RUN_PREVIEW,
    ASSISTED_RUN_RECORDED,
    ASSISTED_RUN_REJECTED,
    CONFIRMATION_PHRASE,
    EVENT_TYPE,
    SUPPORTED_GROUPS,
    build_first_live_evidence_assisted_run,
    first_live_evidence_assisted_runs_path,
    load_first_live_evidence_assisted_runs,
)
from src.app.hammer_radar.operator.first_live_operator_evidence import (
    load_first_live_operator_evidence,
)
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR


class FirstLiveEvidenceAssistedRunTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict(os.environ, {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False)
        self.env_patch.start()

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def _payload(self, **kwargs: object) -> dict[str, object]:
        return build_first_live_evidence_assisted_run(
            candidate_id="candidate-1",
            log_dir=self.log_dir,
            env={},
            **kwargs,
        )

    def test_preview_mode_records_no_evidence_and_keeps_safety_false(self) -> None:
        payload = self._payload(group="sacred_button_review")
        evidence_records = load_first_live_operator_evidence(limit=0, log_dir=self.log_dir)

        self.assertEqual(ASSISTED_RUN_PREVIEW, payload["status"])
        self.assertEqual(["sacred_button_review"], payload["selected_groups"])
        self.assertFalse(payload["execute_evidence_requested"])
        self.assertFalse(payload["live_ready"])
        self.assertFalse(payload["execution_enabled_by_assisted_run"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["execution_attempted"])
        self.assertFalse(payload["real_order_possible"])
        self.assertFalse(payload["secrets_shown"])
        self.assertEqual([], evidence_records)

    def test_execute_mode_without_confirmation_is_rejected(self) -> None:
        payload = self._payload(group="sacred_button_review", execute_evidence=True)

        self.assertEqual(ASSISTED_RUN_REJECTED, payload["status"])
        self.assertFalse(payload["confirmation_valid"])
        self.assertIn("missing or invalid evidence-only confirmation", payload["rejection_reason"])
        self.assertEqual([], load_first_live_operator_evidence(limit=0, log_dir=self.log_dir))

    def test_execute_mode_with_wrong_confirmation_is_rejected(self) -> None:
        payload = self._payload(
            group="sacred_button_review",
            execute_evidence=True,
            confirm_evidence_only="wrong",
        )

        self.assertEqual(ASSISTED_RUN_REJECTED, payload["status"])
        self.assertFalse(payload["confirmation_valid"])
        self.assertEqual([], load_first_live_operator_evidence(limit=0, log_dir=self.log_dir))

    def test_execute_mode_with_exact_confirmation_records_selected_group_only(self) -> None:
        payload = self._payload(
            group="sacred_button_review",
            execute_evidence=True,
            confirm_evidence_only=CONFIRMATION_PHRASE,
        )
        evidence_records = load_first_live_operator_evidence(limit=0, log_dir=self.log_dir)

        self.assertEqual(ASSISTED_RUN_RECORDED, payload["status"])
        self.assertTrue(payload["confirmation_valid"])
        self.assertEqual(["SACRED_BUTTON_INTENT_ONLY_VERIFIED"], payload["planned_evidence_types"]["sacred_button_review"])
        self.assertEqual(1, len(evidence_records))
        self.assertEqual("SACRED_BUTTON_INTENT_ONLY_VERIFIED", evidence_records[0]["evidence_type"])
        self.assertEqual(payload["recorded_evidence_ids"], [evidence_records[0]["evidence_id"]])
        self.assertEqual([], payload["rejected_evidence"])

    def test_unsupported_group_is_rejected(self) -> None:
        payload = self._payload(group="unknown_group")

        self.assertEqual(ASSISTED_RUN_REJECTED, payload["status"])
        self.assertIn("unsupported group: unknown_group", payload["stop_conditions"])
        self.assertEqual([], load_first_live_operator_evidence(limit=0, log_dir=self.log_dir))

    def test_all_groups_mode_plans_all_groups(self) -> None:
        payload = self._payload(all_groups=True)

        self.assertEqual(list(SUPPORTED_GROUPS), payload["selected_groups"])
        self.assertEqual(set(SUPPORTED_GROUPS), set(payload["planned_evidence_types"]))

    def test_evidence_notes_do_not_expose_secrets(self) -> None:
        payload = self._payload(all_groups=True)
        rendered = json.dumps(payload, sort_keys=True)

        self.assertNotIn("secret-api-key-value", rendered)
        self.assertNotIn("secret-api-secret-value", rendered)
        self.assertFalse(payload["secrets_shown"])
        for commands in payload["planned_commands"].values():
            for command in commands:
                note = command.split("--note", 1)[1].lower() if "--note" in command else ""
                self.assertNotIn("api key", note)
                self.assertNotIn("api_secret", note)
                self.assertNotIn("token", note)
                self.assertNotIn("password", note)

    def test_safety_stop_triggers_if_sacred_button_can_place_order_true(self) -> None:
        def unsafe_status_snapshot(**_: object) -> dict[str, object]:
            return {
                "evidence_status": "EVIDENCE_MISSING",
                "recheck_status": "RECHECK_BLOCKED",
                "activation_gate_status": "FIRST_LIVE_BLOCKED",
                "cockpit_status": "COCKPIT_BLOCKED",
                "paper_live_separation_intact": True,
                "sacred_button_can_place_order": True,
                "safety_field_violations": [],
            }

        with patch(
            "src.app.hammer_radar.operator.first_live_evidence_assisted_run._status_snapshot",
            side_effect=unsafe_status_snapshot,
        ):
            payload = self._payload(
                group="sacred_button_review",
                execute_evidence=True,
                confirm_evidence_only=CONFIRMATION_PHRASE,
            )

        self.assertEqual(ASSISTED_RUN_REJECTED, payload["status"])
        self.assertIn("R109 sacred button can_place_order true", payload["stop_conditions"])
        self.assertEqual([], load_first_live_operator_evidence(limit=0, log_dir=self.log_dir))

    def test_safety_stop_triggers_if_paper_live_separation_false(self) -> None:
        def unsafe_status_snapshot(**_: object) -> dict[str, object]:
            return {
                "evidence_status": "EVIDENCE_MISSING",
                "recheck_status": "RECHECK_BLOCKED",
                "activation_gate_status": "FIRST_LIVE_BLOCKED",
                "cockpit_status": "COCKPIT_BLOCKED",
                "paper_live_separation_intact": False,
                "sacred_button_can_place_order": False,
                "safety_field_violations": [],
            }

        with patch(
            "src.app.hammer_radar.operator.first_live_evidence_assisted_run._status_snapshot",
            side_effect=unsafe_status_snapshot,
        ):
            payload = self._payload(
                group="sacred_button_review",
                execute_evidence=True,
                confirm_evidence_only=CONFIRMATION_PHRASE,
            )

        self.assertEqual(ASSISTED_RUN_REJECTED, payload["status"])
        self.assertIn("source reports paper_live_separation_intact false", payload["stop_conditions"])
        self.assertEqual([], load_first_live_operator_evidence(limit=0, log_dir=self.log_dir))

    def test_assisted_run_never_places_orders_or_enables_execution(self) -> None:
        with patch.object(binance_futures_connector, "execute_live_order") as execute_live_order:
            payload = self._payload(
                group="sacred_button_review",
                execute_evidence=True,
                confirm_evidence_only=CONFIRMATION_PHRASE,
            )

        execute_live_order.assert_not_called()
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["execution_attempted"])
        self.assertFalse(payload["real_order_possible"])
        self.assertFalse(payload["execution_enabled_by_assisted_run"])

    def test_ledger_write_contains_safety_fields(self) -> None:
        payload = self._payload(group="sacred_button_review")
        records = load_first_live_evidence_assisted_runs(limit=0, log_dir=self.log_dir)

        self.assertTrue(first_live_evidence_assisted_runs_path(self.log_dir).exists())
        self.assertEqual(1, len(records))
        record = records[0]
        self.assertEqual(EVENT_TYPE, record["event_type"])
        self.assertEqual(payload["assisted_run_id"], record["assisted_run_id"])
        self.assertFalse(record["live_ready"])
        self.assertFalse(record["execution_enabled_by_assisted_run"])
        self.assertFalse(record["order_placed"])
        self.assertFalse(record["execution_attempted"])
        self.assertFalse(record["real_order_possible"])
        self.assertFalse(record["secrets_shown"])

    def test_source_surfaces_include_required_phases(self) -> None:
        payload = self._payload(group="sacred_button_review")
        sources = "\n".join(payload["source_surfaces_used"])

        for phase in ("R112", "R113", "R115", "R106", "R109"):
            self.assertIn(phase, sources)

    def test_paper_live_separation_remains_intact(self) -> None:
        payload = self._payload(group="sacred_button_review")

        self.assertTrue(payload["safety_summary"]["paper_live_separation_intact"])

    def test_inspect_cli_assisted_run_preview_output_json(self) -> None:
        result = subprocess.run(
            [
                ".venv/bin/python",
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                str(self.log_dir),
                "first-live-evidence-assisted-run",
                "--candidate-id",
                "candidate-1",
                "--group",
                "sacred_button_review",
            ],
            cwd=Path(__file__).resolve().parents[2],
            check=True,
            capture_output=True,
            text=True,
        )

        payload = json.loads(result.stdout)
        self.assertEqual(ASSISTED_RUN_PREVIEW, payload["status"])
        self.assertFalse(payload["live_ready"])
        self.assertFalse(payload["execution_enabled_by_assisted_run"])


if __name__ == "__main__":
    unittest.main()
