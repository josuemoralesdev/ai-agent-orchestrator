from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.app.hammer_radar.operator.burn_down_command_pack_sanity import (
    COMMAND_PACK_SAFE,
    COMMAND_PACK_UNSAFE,
    DANGEROUS_COMMAND_TERMS,
    build_burn_down_command_pack_sanity,
    build_next_three_safe_actions,
    validate_safe_command_pack,
)

LANE_KEY = "BTCUSDT|13m|long|ladder_close_50_618"


class BurnDownCommandPackSanityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.tmp.name) / "logs"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_safe_command_pack_returns_safe(self) -> None:
        payload = build_burn_down_command_pack_sanity(
            log_dir=self.log_dir,
            lane_key=LANE_KEY,
            source_statuses=self._source_statuses(),
        )

        self.assertEqual(COMMAND_PACK_SAFE, payload["status"])
        self.assertEqual(0, payload["unsafe_command_count"])
        self.assertEqual([], payload["unsafe_findings"])
        self.assertEqual(LANE_KEY, payload["lane_key"])

    def test_dangerous_command_terms_are_rejected(self) -> None:
        pack = {
            "live_order": "execute_live_order --symbol BTCUSDT",
            "env": "export HAMMER_LIVE=1 && HAMMER_ALLOW_LIVE_ORDERS=true",
            "safe": "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect readiness",
        }
        validation = validate_safe_command_pack(pack)
        terms = {finding["dangerous_term"] for finding in validation["unsafe_findings"]}

        self.assertEqual(2, validation["unsafe_command_count"])
        self.assertEqual(COMMAND_PACK_UNSAFE, COMMAND_PACK_UNSAFE)
        self.assertIn("execute_live_order", terms)
        self.assertIn("export HAMMER_LIVE", terms)
        self.assertIn("HAMMER_ALLOW_LIVE_ORDERS=true", terms)

    def test_all_configured_dangerous_terms_are_rejected(self) -> None:
        pack = {f"cmd_{index}": f"noop {term}" for index, term in enumerate(DANGEROUS_COMMAND_TERMS)}
        validation = validate_safe_command_pack(pack)

        self.assertEqual(len(DANGEROUS_COMMAND_TERMS), validation["unsafe_command_count"])
        self.assertEqual(set(DANGEROUS_COMMAND_TERMS), {item["dangerous_term"] for item in validation["unsafe_findings"]})

    def test_next_three_safe_actions_has_max_three_items(self) -> None:
        burn_down = {
            "dependency_chain": [
                {"title": f"Step {index}", "category": "TEST", "blocked_now": True, "safe_check_command": f"cmd {index}"}
                for index in range(1, 8)
            ],
            "operator_command_pack": {},
        }

        actions = build_next_three_safe_actions(burn_down)

        self.assertEqual(3, len(actions))
        self.assertEqual([1, 2, 3], [item["rank"] for item in actions])

    def test_safety_flags_false(self) -> None:
        payload = build_burn_down_command_pack_sanity(
            log_dir=self.log_dir,
            lane_key=LANE_KEY,
            source_statuses=self._source_statuses(),
        )

        self.assertEqual(
            {
                "order_placed": False,
                "real_order_placed": False,
                "execution_attempted": False,
                "order_payload_created": False,
                "signed_request_created": False,
                "network_allowed": False,
                "secrets_shown": False,
                "env_mutated": False,
                "config_written": False,
            },
            payload["safety"],
        )

    def test_cli_exists(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                str(self.log_dir),
                "burn-down-command-pack-sanity",
                "--lane-key",
                LANE_KEY,
            ],
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": "."},
        )

        payload = json.loads(result.stdout)
        self.assertIn(payload["status"], {COMMAND_PACK_SAFE, COMMAND_PACK_UNSAFE})
        self.assertIn("next_three_safe_actions", payload)
        self.assertIn("safety", payload)

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
                "blockers": ["lane mode is not tiny_live: armed_dry_run"],
                "safety": safety,
            },
            "r130_authorization": {
                "status": "TINY_LIVE_AUTHORIZATION_BLOCKED",
                "blockers": ["recent autonomous paper proof is missing"],
                "safety": safety,
            },
            "r130_authorization_records_summary": {"recorded_count": 0, "latest_status": "MISSING"},
            "r131_kill_switch_rehearsal": {"status": "KILL_SWITCH_REHEARSAL_BLOCKED", "current_blockers": [], "safety": safety},
            "r132_adapter_boundary": {"status": "LIVE_ADAPTER_BOUNDARY_BLOCKED", "main_blockers": [], "safety": safety},
            "r134_dry_authorization": {"status": "DRY_AUTHORIZATION_BLOCKED", "blockers": [], "safety": safety},
            "r135_adapter_rehearsal": {"status": "LIVE_ADAPTER_REHEARSAL_BLOCKED", "main_blockers": [], "safety": safety},
            "r136_protective_policy": {"status": "PROTECTIVE_POLICY_BLOCKED", "main_blockers": [], "safety": safety},
            "r137_protective_preview": {"status": "PROTECTIVE_PAYLOAD_BLOCKED", "main_blockers": [], "safety": safety},
            "final_live_preflight": {"status": "BLOCKED", "blockers": ["live execution disabled"], "safety": safety},
            "first_live_activation_gate": {"status": "FIRST_LIVE_BLOCKED", "blockers": [], "safety": safety},
            "live_env_boundary": {"boundary_status": "LIVE_ENV_ARMING_NOT_ALLOWED_YET", "blockers": [], "safety": safety},
            "live_arming_preflight": {"final_preflight_status": "BLOCKED_BY_LIVE_ENV_LOCKS", "blockers": [], "safety": safety},
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
                "blockers": [],
            },
            "source_surfaces_used": ["test_fixture"],
        }


if __name__ == "__main__":
    unittest.main()
