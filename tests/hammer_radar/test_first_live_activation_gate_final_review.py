from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.execution import binance_futures_connector
from src.app.hammer_radar.operator.first_live_activation_gate_final_review import (
    FINAL_REVIEW_BLOCKED,
    FINAL_REVIEW_PARTIAL,
    READY_TO_REQUEST_FIRST_LIVE_AUTHORIZATION,
    build_first_live_activation_final_review,
    first_live_activation_final_reviews_path,
    format_first_live_activation_final_review_text,
    load_first_live_activation_final_reviews,
)
from src.app.hammer_radar.operator.first_live_operator_evidence import REQUIRED_EVIDENCE_TYPES
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR


class FirstLiveActivationGateFinalReviewTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict(os.environ, {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False)
        self.env_patch.start()

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def _tuple(self) -> dict[str, str]:
        return {
            "candidate_id": "candidate-1",
            "risk_contract_hash": "risk-1",
            "packet_hash": "packet-1",
        }

    def _final_preflight(self, *, ready: bool = True, paper_live_separation_intact: bool = True) -> dict[str, object]:
        return {
            "status": "READY" if ready else "BLOCKED",
            "candidate_id": "candidate-1",
            "risk_contract_hash": "risk-1",
            "final_review_packet_hash": "packet-1",
            "blockers": [] if ready else ["stale candidate risk"],
            "protective_orders_ready": True,
            "paper_live_separation_intact": paper_live_separation_intact,
            "live_ready": False,
            "order_placed": False,
            "real_order_placed": False,
            "execution_attempted": False,
            "real_order_possible": False,
            "secrets_shown": False,
            "source_surfaces_used": ["R102 final-live-preflight"],
        }

    def _dry_run(self, *, ready: bool = True) -> dict[str, object]:
        return {
            **self._tuple(),
            "status": "READY_FOR_DRY_RUN" if ready else "BLOCKED_FOR_DRY_RUN",
            "live_ready": False,
            "order_placed": False,
            "real_order_placed": False,
            "execution_attempted": False,
            "real_order_possible": False,
            "secrets_shown": False,
            "paper_live_separation_intact": True,
            "source_surfaces_used": ["R104 tiny-live-armed-dry-run"],
        }

    def _protocol(self, *, ready: bool = True) -> dict[str, object]:
        return {
            **self._tuple(),
            "status": "PROTOCOL_PREREQS_READY" if ready else "PROTOCOL_BLOCKED",
            "live_ready": False,
            "order_placed": False,
            "real_order_placed": False,
            "execution_attempted": False,
            "real_order_possible": False,
            "secrets_shown": False,
            "paper_live_separation_intact": True,
            "source_surfaces_used": ["R105 one-tiny-live-order-protocol"],
        }

    def _activation_gate(
        self,
        *,
        ready: bool = True,
        order_placed: bool = False,
        paper_live_separation_intact: bool = True,
    ) -> dict[str, object]:
        return {
            **self._tuple(),
            "status": "FIRST_LIVE_ACTIVATION_READY" if ready else "FIRST_LIVE_BLOCKED",
            "blockers": [] if ready else ["approval intent missing"],
            "live_ready": False,
            "execution_enabled_by_gate": False,
            "order_placed": order_placed,
            "real_order_placed": False,
            "execution_attempted": False,
            "real_order_possible": False,
            "secrets_shown": False,
            "paper_live_separation_intact": paper_live_separation_intact,
            "source_surfaces_used": ["R106 first-live-activation-gate"],
        }

    def _cockpit(
        self,
        *,
        can_place_order: bool = False,
        records_intent_only: bool = True,
        paper_live_separation_intact: bool = True,
    ) -> dict[str, object]:
        return {
            **self._tuple(),
            "status": "COCKPIT_READY",
            "sacred_button_state": {
                "can_place_order": can_place_order,
                "records_intent_only": records_intent_only,
            },
            "backend_authority": {
                "sacred_button_can_place_order": can_place_order,
            },
            "live_ready": False,
            "execution_enabled_by_ui": False,
            "order_placed": False,
            "real_order_placed": False,
            "execution_attempted": False,
            "real_order_possible": False,
            "secrets_shown": False,
            "paper_live_separation_intact": paper_live_separation_intact,
            "source_surfaces_used": ["R109 cockpit"],
        }

    def _evidence(self, *, ready: bool = True, partial: bool = False) -> dict[str, object]:
        present = list(REQUIRED_EVIDENCE_TYPES if ready else REQUIRED_EVIDENCE_TYPES[:2] if partial else [])
        missing = [item for item in REQUIRED_EVIDENCE_TYPES if item not in present]
        return {
            "status": "EVIDENCE_READY_FOR_PREREQ_RECHECK" if ready else "EVIDENCE_PARTIAL" if partial else "EVIDENCE_MISSING",
            "records_count": len(present),
            "accepted_records_count": len(present),
            "rejected_records_count": 0,
            "evidence_types_present": present,
            "evidence_types_missing": missing,
            "ready_tuple": self._tuple() if ready else None,
            "live_ready": False,
            "execution_enabled_by_evidence": False,
            "order_placed": False,
            "real_order_placed": False,
            "execution_attempted": False,
            "real_order_possible": False,
            "secrets_shown": False,
        }

    def _recheck(self, *, ready: bool = True, partial: bool = False) -> dict[str, object]:
        return {
            "status": "RECHECK_READY_FOR_R106" if ready else "RECHECK_PARTIAL" if partial else "RECHECK_BLOCKED",
            "recheck_tuple": self._tuple(),
            "live_ready": False,
            "execution_enabled_by_recheck": False,
            "order_placed": False,
            "real_order_placed": False,
            "execution_attempted": False,
            "real_order_possible": False,
            "secrets_shown": False,
            "paper_live_separation_intact": True,
            "source_surfaces_used": ["R113 first-live-prerequisite-recheck-after-evidence"],
        }

    def _post_evidence(self, *, ready: bool = True, partial: bool = False) -> dict[str, object]:
        return {
            "status": "POST_EVIDENCE_READY_FOR_ACTIVATION_GATE_RECHECK" if ready else "POST_EVIDENCE_PARTIAL" if partial else "POST_EVIDENCE_BLOCKED",
            "active_tuple": {**self._tuple(), "tuple_status": "CONSISTENT", "source": "test"},
            "live_ready": False,
            "execution_enabled_by_post_evidence_recheck": False,
            "order_placed": False,
            "real_order_placed": False,
            "execution_attempted": False,
            "real_order_possible": False,
            "secrets_shown": False,
            "paper_live_separation_intact": True,
            "source_surfaces_used": ["R117 first-live-post-evidence-gate-recheck"],
        }

    def _source_patches(
        self,
        *,
        final_preflight_ready: bool = True,
        dry_run_ready: bool = True,
        protocol_ready: bool = True,
        activation_ready: bool = True,
        evidence_ready: bool = True,
        evidence_partial: bool = False,
        recheck_ready: bool = True,
        recheck_partial: bool = False,
        post_ready: bool = True,
        post_partial: bool = False,
        sacred_can_place_order: bool = False,
        sacred_records_intent_only: bool = True,
        paper_live_separation_intact: bool = True,
        order_placed: bool = False,
    ):
        module = "src.app.hammer_radar.operator.first_live_activation_gate_final_review"
        return (
            patch(f"{module}.build_final_live_preflight", return_value=self._final_preflight(ready=final_preflight_ready, paper_live_separation_intact=paper_live_separation_intact)),
            patch(f"{module}.build_tiny_live_armed_dry_run", return_value=self._dry_run(ready=dry_run_ready)),
            patch(f"{module}.build_one_tiny_live_order_protocol_check", return_value=self._protocol(ready=protocol_ready)),
            patch(f"{module}.build_first_live_activation_gate", return_value=self._activation_gate(ready=activation_ready, order_placed=order_placed, paper_live_separation_intact=paper_live_separation_intact)),
            patch(
                f"{module}.build_operator_approval_cockpit_state",
                return_value=self._cockpit(
                    can_place_order=sacred_can_place_order,
                    records_intent_only=sacred_records_intent_only,
                    paper_live_separation_intact=paper_live_separation_intact,
                ),
            ),
            patch(f"{module}.build_first_live_evidence_status", return_value=self._evidence(ready=evidence_ready, partial=evidence_partial)),
            patch(f"{module}.build_first_live_prerequisite_recheck_after_evidence", return_value=self._recheck(ready=recheck_ready, partial=recheck_partial)),
            patch(f"{module}.load_first_live_evidence_assisted_runs", return_value=[{"status": "ASSISTED_RUN_RECORDED"}]),
            patch(f"{module}.build_first_live_post_evidence_gate_recheck", return_value=self._post_evidence(ready=post_ready, partial=post_partial)),
        )

    def _build_with_patches(self, **kwargs: object) -> dict[str, object]:
        patches = self._source_patches(**kwargs)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8]:
            return build_first_live_activation_final_review(candidate_id="candidate-1", log_dir=self.log_dir)

    def test_final_review_returns_required_safety_state(self) -> None:
        payload = self._build_with_patches()

        self.assertFalse(payload["live_ready"])
        self.assertFalse(payload["execution_enabled_by_final_review"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["execution_attempted"])
        self.assertFalse(payload["real_order_possible"])
        self.assertFalse(payload["secrets_shown"])

    def test_final_review_never_places_orders(self) -> None:
        with patch.object(binance_futures_connector, "execute_live_order") as execute_live_order:
            payload = self._build_with_patches()

        execute_live_order.assert_not_called()
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["execution_attempted"])

    def test_includes_required_sections(self) -> None:
        payload = self._build_with_patches()

        self.assertEqual(
            {
                "R102 final preflight",
                "R104 tiny live armed dry run",
                "R105 protocol",
                "R106 activation gate",
                "R109 cockpit",
                "R112 evidence status",
                "R113 prerequisite recheck",
                "R116 assisted run latest status",
                "R117 post-evidence recheck",
            },
            set(payload["source_statuses"]),
        )
        self.assertIn("readiness_matrix", payload)
        self.assertIn("authorization_request_readiness", payload)
        self.assertIn("final_operator_readiness_checklist", payload)
        self.assertIn("authorization_boundary", payload)
        self.assertIn("final_recheck_command_pack", payload)

    def test_blocked_when_r106_is_blocked(self) -> None:
        payload = self._build_with_patches(activation_ready=False)

        self.assertEqual(FINAL_REVIEW_BLOCKED, payload["status"])
        self.assertFalse(payload["authorization_request_readiness"]["can_request_authorization"])

    def test_partial_when_evidence_improves_but_post_evidence_is_not_ready(self) -> None:
        payload = self._build_with_patches(
            evidence_ready=False,
            evidence_partial=True,
            recheck_ready=False,
            recheck_partial=True,
            post_ready=False,
            post_partial=True,
        )

        self.assertEqual(FINAL_REVIEW_PARTIAL, payload["status"])
        self.assertFalse(payload["authorization_request_readiness"]["can_request_authorization"])

    def test_ready_only_when_all_surfaces_ready_and_safety_clean(self) -> None:
        payload = self._build_with_patches()

        self.assertEqual(READY_TO_REQUEST_FIRST_LIVE_AUTHORIZATION, payload["status"])
        self.assertTrue(payload["authorization_request_readiness"]["can_request_authorization"])
        self.assertFalse(payload["live_ready"])

    def test_sacred_button_can_place_order_true_forces_blocked(self) -> None:
        payload = self._build_with_patches(sacred_can_place_order=True)

        self.assertEqual(FINAL_REVIEW_BLOCKED, payload["status"])
        self.assertFalse(payload["authorization_request_readiness"]["can_request_authorization"])

    def test_paper_live_separation_false_forces_blocked(self) -> None:
        payload = self._build_with_patches(paper_live_separation_intact=False)

        self.assertEqual(FINAL_REVIEW_BLOCKED, payload["status"])
        self.assertFalse(payload["paper_live_separation_intact"])

    def test_order_safety_violation_forces_blocked(self) -> None:
        payload = self._build_with_patches(order_placed=True)

        self.assertEqual(FINAL_REVIEW_BLOCKED, payload["status"])
        self.assertFalse(payload["order_placed"])
        self.assertTrue(
            any(item["source"] == "no_order_safety" for item in payload["remaining_blockers"])
        )

    def test_ledger_write_contains_safety_fields(self) -> None:
        payload = self._build_with_patches()
        records = load_first_live_activation_final_reviews(limit=0, log_dir=self.log_dir)

        self.assertEqual(1, len(records))
        record = records[0]
        self.assertEqual(payload["final_review_id"], record["final_review_id"])
        self.assertFalse(record["live_ready"])
        self.assertFalse(record["execution_enabled_by_final_review"])
        self.assertFalse(record["order_placed"])
        self.assertFalse(record["real_order_placed"])
        self.assertFalse(record["execution_attempted"])
        self.assertFalse(record["real_order_possible"])
        self.assertFalse(record["secrets_shown"])
        self.assertEqual(first_live_activation_final_reviews_path(self.log_dir), self.log_dir / "first_live_activation_final_reviews.ndjson")

    def test_paper_live_separation_remains_intact_when_sources_are_clean(self) -> None:
        payload = self._build_with_patches()

        self.assertTrue(payload["paper_live_separation_intact"])
        self.assertTrue(
            next(item for item in payload["readiness_matrix"] if item["layer"] == "paper_live_separation")["satisfied"]
        )

    def test_format_does_not_expose_secret_tokens(self) -> None:
        payload = self._build_with_patches()
        payload["source_statuses"]["secret-api"] = "present"
        rendered = format_first_live_activation_final_review_text(payload)

        self.assertFalse(json.loads(rendered)["secrets_shown"])

    def test_cli_outputs_json(self) -> None:
        command = [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(self.log_dir),
            "first-live-activation-final-review",
            "--no-record",
        ]
        result = subprocess.run(command, check=True, capture_output=True, text=True, env={**os.environ, "PYTHONPATH": "."})
        payload = json.loads(result.stdout)

        self.assertIn(payload["status"], {FINAL_REVIEW_BLOCKED, FINAL_REVIEW_PARTIAL, READY_TO_REQUEST_FIRST_LIVE_AUTHORIZATION})
        self.assertFalse(payload["live_ready"])
        self.assertFalse(payload["execution_enabled_by_final_review"])


if __name__ == "__main__":
    unittest.main()
