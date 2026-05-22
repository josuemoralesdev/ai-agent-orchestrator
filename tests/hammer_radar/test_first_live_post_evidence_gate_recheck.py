from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.execution import binance_futures_connector
from src.app.hammer_radar.operator.first_live_operator_evidence import REQUIRED_EVIDENCE_TYPES
from src.app.hammer_radar.operator.first_live_post_evidence_gate_recheck import (
    EVENT_TYPE,
    POST_EVIDENCE_BLOCKED,
    POST_EVIDENCE_PARTIAL,
    POST_EVIDENCE_READY_FOR_ACTIVATION_GATE_RECHECK,
    build_first_live_post_evidence_gate_recheck,
    first_live_post_evidence_gate_rechecks_path,
    format_first_live_post_evidence_gate_recheck_text,
    load_first_live_post_evidence_gate_rechecks,
)
from src.app.hammer_radar.operator.first_live_prerequisite_clearing import GROUP_ORDER
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR


class FirstLivePostEvidenceGateRecheckTestCase(unittest.TestCase):
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

    def _evidence_status(self, *, ready: bool = False, partial: bool = False) -> dict[str, object]:
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
            "execution_attempted": False,
            "real_order_possible": False,
            "secrets_shown": False,
        }

    def _recheck(self, *, ready: bool = False, partial: bool = False) -> dict[str, object]:
        blocker_recheck = []
        for group in GROUP_ORDER:
            if ready or (partial and group in {"approval_records", "sacred_button_safety"}):
                status = "CLEAR"
                blockers: list[str] = []
            else:
                status = "NEEDS_MORE_EVIDENCE"
                blockers = [f"{group} evidence incomplete"]
            blocker_recheck.append(
                {
                    "group": group,
                    "rechecked_status": status,
                    "evidence_types_used": [],
                    "blockers_remaining": blockers,
                    "next_action": f"clear {group}",
                    "verification_command": f"verify {group}",
                }
            )
        return {
            "status": "RECHECK_READY_FOR_R106" if ready else "RECHECK_PARTIAL" if partial else "RECHECK_BLOCKED",
            "recheck_tuple": self._tuple(),
            "blocker_recheck": blocker_recheck,
            "cleared_groups": [item["group"] for item in blocker_recheck if item["rechecked_status"] == "CLEAR"],
            "evidence_needed_groups": [item["group"] for item in blocker_recheck if item["rechecked_status"] == "NEEDS_MORE_EVIDENCE"],
            "live_ready": False,
            "execution_enabled_by_recheck": False,
            "order_placed": False,
            "execution_attempted": False,
            "real_order_possible": False,
            "secrets_shown": False,
            "paper_live_separation_intact": True,
            "source_surfaces_used": ["R113 first-live-prerequisite-recheck-after-evidence"],
        }

    def _activation_gate(self, *, ready: bool = False, paper_live_separation_intact: bool = True) -> dict[str, object]:
        return {
            **self._tuple(),
            "status": "FIRST_LIVE_ACTIVATION_READY" if ready else "FIRST_LIVE_BLOCKED",
            "blockers": [] if ready else ["approval intent missing"],
            "live_ready": False,
            "execution_enabled_by_gate": False,
            "order_placed": False,
            "real_order_placed": False,
            "execution_attempted": False,
            "real_order_possible": False,
            "secrets_shown": False,
            "paper_live_separation_intact": paper_live_separation_intact,
            "source_surfaces_used": ["R106 first-live-activation-gate"],
        }

    def _cockpit(self, *, can_place_order: bool = False, paper_live_separation_intact: bool = True) -> dict[str, object]:
        return {
            **self._tuple(),
            "status": "COCKPIT_READY",
            "sacred_button_state": {
                "can_place_order": can_place_order,
                "records_intent_only": True,
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

    def _source_patches(
        self,
        *,
        evidence_ready: bool = False,
        evidence_partial: bool = False,
        recheck_ready: bool = False,
        recheck_partial: bool = False,
        activation_ready: bool = False,
        sacred_can_place_order: bool = False,
        paper_live_separation_intact: bool = True,
    ):
        return (
            patch(
                "src.app.hammer_radar.operator.first_live_post_evidence_gate_recheck.build_first_live_evidence_status",
                return_value=self._evidence_status(ready=evidence_ready, partial=evidence_partial),
            ),
            patch(
                "src.app.hammer_radar.operator.first_live_post_evidence_gate_recheck.build_first_live_prerequisite_recheck_after_evidence",
                return_value=self._recheck(ready=recheck_ready, partial=recheck_partial),
            ),
            patch(
                "src.app.hammer_radar.operator.first_live_post_evidence_gate_recheck.load_first_live_evidence_assisted_runs",
                return_value=[{"status": "ASSISTED_RUN_RECORDED"}],
            ),
            patch(
                "src.app.hammer_radar.operator.first_live_post_evidence_gate_recheck.build_first_live_prerequisite_clearing",
                return_value={"status": "PREREQS_BLOCKED", "paper_live_separation_intact": paper_live_separation_intact},
            ),
            patch(
                "src.app.hammer_radar.operator.first_live_post_evidence_gate_recheck.build_first_live_burn_down",
                return_value={"status": "BURN_DOWN_READY", "source_surfaces_used": ["R110 first-live-burn-down"]},
            ),
            patch(
                "src.app.hammer_radar.operator.first_live_post_evidence_gate_recheck.build_first_live_activation_gate",
                return_value=self._activation_gate(ready=activation_ready, paper_live_separation_intact=paper_live_separation_intact),
            ),
            patch(
                "src.app.hammer_radar.operator.first_live_post_evidence_gate_recheck.build_operator_approval_cockpit_state",
                return_value=self._cockpit(can_place_order=sacred_can_place_order, paper_live_separation_intact=paper_live_separation_intact),
            ),
        )

    def _build_with_patches(self, **kwargs: object) -> dict[str, object]:
        patches = self._source_patches(**kwargs)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
            return build_first_live_post_evidence_gate_recheck(
                candidate_id="candidate-1",
                log_dir=self.log_dir,
            )

    def test_post_evidence_recheck_returns_required_safety_state(self) -> None:
        payload = self._build_with_patches()

        self.assertEqual(POST_EVIDENCE_BLOCKED, payload["status"])
        self.assertFalse(payload["live_ready"])
        self.assertFalse(payload["execution_enabled_by_post_evidence_recheck"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["execution_attempted"])
        self.assertFalse(payload["real_order_possible"])
        self.assertFalse(payload["secrets_shown"])

    def test_post_evidence_recheck_never_places_orders(self) -> None:
        with patch.object(binance_futures_connector, "execute_live_order") as execute_live_order:
            payload = self._build_with_patches(evidence_partial=True, recheck_partial=True)

        execute_live_order.assert_not_called()
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["execution_attempted"])

    def test_source_statuses_evidence_summary_gate_delta_and_activation_summary_are_included(self) -> None:
        payload = self._build_with_patches(evidence_partial=True, recheck_partial=True)

        self.assertEqual(
            {
                "R112 evidence status",
                "R113 prerequisite recheck",
                "R116 assisted run status",
                "R111 prerequisite clearing",
                "R110 burn-down",
                "R106 activation gate",
                "R109 cockpit",
            },
            set(payload["source_statuses"]),
        )
        self.assertIn("records_count", payload["evidence_summary"])
        self.assertIn("blockers_remaining_count", payload["gate_delta"])
        self.assertIn("can_consider_activation_phase", payload["activation_readiness_summary"])
        self.assertEqual(GROUP_ORDER, [item["group"] for item in payload["blocker_map"]])

    def test_post_evidence_blocked_when_r106_is_blocked(self) -> None:
        payload = self._build_with_patches(evidence_ready=True, recheck_ready=True, activation_ready=False)

        self.assertEqual(POST_EVIDENCE_BLOCKED, payload["status"])
        self.assertEqual("FIRST_LIVE_BLOCKED", payload["gate_delta"]["r106_current_status"])

    def test_post_evidence_partial_when_evidence_is_accepted_but_gate_blockers_remain(self) -> None:
        payload = self._build_with_patches(
            evidence_partial=True,
            recheck_partial=True,
            activation_ready=True,
        )

        self.assertEqual(POST_EVIDENCE_PARTIAL, payload["status"])
        self.assertGreater(payload["evidence_summary"]["accepted_records_count"], 0)
        self.assertGreater(payload["gate_delta"]["blockers_remaining_count"], 0)

    def test_post_evidence_ready_only_when_evidence_ready_and_safety_clean(self) -> None:
        payload = self._build_with_patches(
            evidence_ready=True,
            recheck_ready=True,
            activation_ready=True,
        )

        self.assertEqual(POST_EVIDENCE_READY_FOR_ACTIVATION_GATE_RECHECK, payload["status"])
        self.assertFalse(payload["live_ready"])
        self.assertTrue(payload["activation_readiness_summary"]["can_consider_activation_phase"])

    def test_sacred_button_can_place_order_true_forces_blocked(self) -> None:
        payload = self._build_with_patches(
            evidence_ready=True,
            recheck_ready=True,
            activation_ready=True,
            sacred_can_place_order=True,
        )

        self.assertEqual(POST_EVIDENCE_BLOCKED, payload["status"])
        self.assertTrue(payload["activation_readiness_summary"]["sacred_button_can_place_order"])

    def test_paper_live_separation_false_forces_blocked(self) -> None:
        payload = self._build_with_patches(
            evidence_ready=True,
            recheck_ready=True,
            activation_ready=True,
            paper_live_separation_intact=False,
        )

        self.assertEqual(POST_EVIDENCE_BLOCKED, payload["status"])
        self.assertFalse(payload["activation_readiness_summary"]["paper_live_separation_intact"])

    def test_ledger_write_contains_required_safety_fields(self) -> None:
        payload = self._build_with_patches(evidence_partial=True, recheck_partial=True)
        records = load_first_live_post_evidence_gate_rechecks(limit=0, log_dir=self.log_dir)

        self.assertTrue(first_live_post_evidence_gate_rechecks_path(self.log_dir).exists())
        self.assertEqual(1, len(records))
        record = records[0]
        self.assertEqual(EVENT_TYPE, record["event_type"])
        self.assertEqual(payload["post_evidence_recheck_id"], record["post_evidence_recheck_id"])
        self.assertFalse(record["live_ready"])
        self.assertFalse(record["execution_enabled_by_post_evidence_recheck"])
        self.assertFalse(record["order_placed"])
        self.assertFalse(record["real_order_placed"])
        self.assertFalse(record["execution_attempted"])
        self.assertFalse(record["real_order_possible"])
        self.assertFalse(record["secrets_shown"])

    def test_secrets_are_not_exposed_and_formatter_returns_json(self) -> None:
        env = {
            "BINANCE_API_KEY": "secret-api-key-value",
            "BINANCE_API_SECRET": "secret-api-secret-value",
            "TELEGRAM_BOT_TOKEN": "secret-telegram-token",
        }
        payload = build_first_live_post_evidence_gate_recheck(
            candidate_id="candidate-1",
            log_dir=self.log_dir,
            env=env,
            record=False,
        )
        rendered = format_first_live_post_evidence_gate_recheck_text(payload)

        self.assertNotIn("secret-api-key-value", rendered)
        self.assertNotIn("secret-api-secret-value", rendered)
        self.assertNotIn("secret-telegram-token", rendered)
        self.assertFalse(json.loads(rendered)["secrets_shown"])

    def test_inspect_cli_post_evidence_recheck_output_json(self) -> None:
        result = subprocess.run(
            [
                ".venv/bin/python",
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                str(self.log_dir),
                "first-live-post-evidence-gate-recheck",
                "--candidate-id",
                "candidate-1",
            ],
            cwd=Path(__file__).resolve().parents[2],
            check=True,
            capture_output=True,
            text=True,
        )

        payload = json.loads(result.stdout)
        self.assertEqual(POST_EVIDENCE_BLOCKED, payload["status"])
        self.assertFalse(payload["live_ready"])
        self.assertFalse(payload["execution_enabled_by_post_evidence_recheck"])
        self.assertIn("final_recheck_command_pack", payload)


if __name__ == "__main__":
    unittest.main()
