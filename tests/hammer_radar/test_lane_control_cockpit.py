from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator import lane_control_cockpit
from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.lane_control_cockpit import (
    DEFAULT_LANE_KEY,
    build_lane_control_cockpit_state,
    build_cockpit_command_pack,
    render_lane_control_cockpit_html,
)


class LaneControlCockpitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.tmp.name) / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_cockpit_state_is_read_only_and_safe(self) -> None:
        payload = build_lane_control_cockpit_state(log_dir=self.log_dir)

        self.assertIn(payload["status"], {"LANE_COCKPIT_READY", "LANE_COCKPIT_DEGRADED"})
        self.assertIs(payload["read_only"], True)
        self.assertIs(payload["no_order_buttons"], True)
        self.assertTrue(payload["safety"]["paper_live_separation_intact"])
        for key in (
            "order_placed",
            "real_order_placed",
            "execution_attempted",
            "order_payload_created",
            "network_allowed",
            "secrets_shown",
            "env_mutated",
            "config_written",
            "global_live_flags_changed",
            "binance_order_endpoint_called",
            "signed_request_created",
        ):
            self.assertFalse(payload["safety"][key])
            self.assertFalse(payload["global_safety"].get(key, False))

    def test_command_pack_contains_only_safe_copy_commands(self) -> None:
        pack = build_cockpit_command_pack(log_dir=self.log_dir, lane_key=DEFAULT_LANE_KEY)

        for key in (
            "lane-control-status",
            "fresh-signal-router-status",
            "lane-autonomy-scheduler",
            "autonomous-paper-lane-executor-integration-preview",
            "first-tiny-live-lane-execution-gate",
            "first-tiny-live-autonomous-lane-authorization-preview",
            "live-lane-kill-switch-rehearsal",
            "live-adapter-boundary-final-review",
        ):
            self.assertIn(key, pack)

        rendered = "\n".join(pack.values()).lower()
        for forbidden in (
            "binance-live",
            "payload-preview",
            "test-order",
            "execute-paper",
            " execute",
            "--apply",
            "--record",
            "--confirm",
            "env-boundary-review",
            "lane-control-command",
        ):
            self.assertNotIn(forbidden, rendered)

    def test_lane_cards_selected_lane_boundary_and_next_action_are_included(self) -> None:
        payload = build_lane_control_cockpit_state(log_dir=self.log_dir)

        lane_keys = {lane["lane_key"] for lane in payload["lanes"]}
        self.assertIn(DEFAULT_LANE_KEY, lane_keys)
        self.assertEqual(DEFAULT_LANE_KEY, payload["selected_lane"]["lane_key"])
        self.assertIn("tiny_live_gate_summary", payload["selected_lane"])
        self.assertIn("adapter_boundary_summary", payload)
        self.assertIn("next_action", payload)
        self.assertTrue(payload["next_action"]["safe_command"].startswith("PYTHONPATH=."))

    def test_html_renders_control_tower_without_dangerous_actions(self) -> None:
        html = render_lane_control_cockpit_html()
        lowered = html.lower()

        self.assertIn("Hammer Control Tower", html)
        self.assertIn("Sacred Gate Panel", html)
        self.assertIn("READ ONLY", html)
        self.assertIn("NO ORDER BUTTON", html)
        self.assertNotIn("<form", lowered)
        self.assertNotIn("action=", lowered)
        self.assertNotIn("place order", lowered)
        self.assertNotIn("enable live", lowered)
        self.assertNotIn("method: 'post'", lowered)
        self.assertNotIn('method: "post"', lowered)

    def test_state_and_html_routes_exist(self) -> None:
        state_response = self.client.get("/operator/lane-cockpit/state")
        html_response = self.client.get("/operator/lane-cockpit")

        self.assertEqual(200, state_response.status_code)
        self.assertEqual(200, html_response.status_code)
        self.assertTrue(state_response.json()["read_only"])
        self.assertIn("Hammer Control Tower", html_response.text)

    def test_cli_mode_exists_and_returns_compact_state(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                str(self.log_dir),
                "lane-control-cockpit-state",
            ],
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": "."},
        )

        payload = json.loads(result.stdout)
        self.assertTrue(payload["read_only"])
        self.assertTrue(payload["no_order_buttons"])
        self.assertIn("global_safety", payload)
        self.assertIn("command_pack", payload)

    def test_degraded_state_remains_safe_if_source_fails(self) -> None:
        with patch.object(lane_control_cockpit, "build_lane_control_status", side_effect=RuntimeError("boom")):
            payload = build_lane_control_cockpit_state(log_dir=self.log_dir)

        self.assertEqual("LANE_COCKPIT_DEGRADED", payload["status"])
        self.assertTrue(payload["read_only"])
        self.assertTrue(payload["no_order_buttons"])
        self.assertEqual("lane_control_status", payload["source_failures"][0]["source"])
        self.assertFalse(payload["safety"]["order_placed"])
        self.assertFalse(payload["safety"]["real_order_placed"])
        self.assertFalse(payload["safety"]["execution_attempted"])
        self.assertFalse(payload["safety"]["network_allowed"])
        self.assertFalse(payload["safety"]["secrets_shown"])
        self.assertTrue(payload["safety"]["paper_live_separation_intact"])


if __name__ == "__main__":
    unittest.main()
