from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.app.hammer_radar.operator.lane_command_interface import (
    CONFIRM_LANE_CHANGE_PHRASE,
    LANE_COMMAND_APPLIED,
    LANE_COMMAND_LIST,
    LANE_COMMAND_PREVIEW,
    LANE_COMMAND_REJECTED,
    apply_lane_command,
)
from src.app.hammer_radar.operator.strategy_performance import ELIGIBLE_FOR_FUTURE_TINY_LIVE


LANE_KEY = "BTCUSDT|13m|long|ladder_close_50_618"


class LaneCommandInterfaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.config_path = self.root / "lane_controls.json"
        self.log_dir = self.root / "logs"
        self.config = {
            "schema_version": "1.0",
            "default_mode": "disabled",
            "notes": ["test config"],
            "lanes": [
                {
                    "symbol": "BTCUSDT",
                    "timeframe": "13m",
                    "direction": "long",
                    "entry_mode": "ladder_close_50_618",
                    "mode": "paper",
                    "max_daily_trades": 1,
                    "max_daily_loss_pct": 0.25,
                    "freshness_seconds": 120,
                    "cooldown_after_loss_minutes": 120,
                    "require_protective_orders": True,
                }
            ],
        }
        self._write_config(self.config)
        self.matrix = {
            "recommendations": [
                {
                    "timeframe": "13m",
                    "direction": "long",
                    "entry_mode": "ladder_close_50_618",
                    "recommendation": ELIGIBLE_FOR_FUTURE_TINY_LIVE,
                    "sample_count": 50,
                    "win_rate_pct": 60.0,
                    "avg_pnl_pct": 0.2,
                    "total_pnl_pct": 10.0,
                    "blockers": [],
                }
            ]
        }

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_list_action_returns_current_lanes(self) -> None:
        payload = self._command(action="list")

        self.assertEqual(LANE_COMMAND_LIST, payload["status"])
        self.assertEqual(1, payload["configured_lanes_count"])
        self.assertEqual(LANE_KEY, payload["lanes"][0]["lane_key"])
        self.assertFalse(payload["config_written"])

    def test_preview_set_mode_does_not_write_config(self) -> None:
        payload = self._command(action="preview-set-mode", lane_key=LANE_KEY, mode="armed_dry_run")

        self.assertEqual(LANE_COMMAND_PREVIEW, payload["status"])
        self.assertEqual("paper", payload["previous_mode"])
        self.assertEqual("armed_dry_run", payload["resulting_mode"])
        self.assertEqual("paper", self._read_config()["lanes"][0]["mode"])
        self.assertFalse((self.log_dir / "lane_control_commands.ndjson").exists())

    def test_set_mode_without_apply_does_not_write_config(self) -> None:
        payload = self._command(action="set-mode", lane_key=LANE_KEY, mode="armed_dry_run")

        self.assertEqual(LANE_COMMAND_PREVIEW, payload["status"])
        self.assertFalse(payload["config_written"])
        self.assertEqual("paper", self._read_config()["lanes"][0]["mode"])

    def test_set_mode_with_wrong_confirmation_is_rejected(self) -> None:
        payload = self._command(
            action="set-mode",
            lane_key=LANE_KEY,
            mode="armed_dry_run",
            apply=True,
            confirm_lane_change="wrong",
        )

        self.assertEqual(LANE_COMMAND_REJECTED, payload["status"])
        self.assertIn("exact lane config change confirmation phrase is required for apply", payload["blockers"])
        self.assertFalse(payload["config_written"])
        self.assertEqual("paper", self._read_config()["lanes"][0]["mode"])

    def test_set_mode_with_exact_confirmation_writes_only_mode(self) -> None:
        before = self._read_config()["lanes"][0]
        payload = self._command(
            action="set-mode",
            lane_key=LANE_KEY,
            mode="armed_dry_run",
            apply=True,
            confirm_lane_change=CONFIRM_LANE_CHANGE_PHRASE,
        )
        after = self._read_config()["lanes"][0]

        self.assertEqual(LANE_COMMAND_APPLIED, payload["status"])
        self.assertTrue(payload["config_written"])
        self.assertEqual("armed_dry_run", after["mode"])
        for key, value in before.items():
            if key != "mode":
                self.assertEqual(value, after[key])

    def test_invalid_mode_rejected(self) -> None:
        payload = self._command(action="set-mode", lane_key=LANE_KEY, mode="live_now")

        self.assertEqual(LANE_COMMAND_REJECTED, payload["status"])
        self.assertIn("invalid requested lane mode: live_now", payload["blockers"])

    def test_unknown_lane_rejected(self) -> None:
        payload = self._command(action="set-mode", lane_key="ETHUSDT|13m|long|ladder_close_50_618", mode="paper")

        self.assertEqual(LANE_COMMAND_REJECTED, payload["status"])
        self.assertIn("unknown lane_key; R124 rejects unknown lanes by default", payload["blockers"])

    def test_request_tiny_live_requires_request_flag(self) -> None:
        payload = self._command(action="request-tiny-live-mode", lane_key=LANE_KEY, mode="tiny_live")

        self.assertEqual(LANE_COMMAND_REJECTED, payload["status"])
        self.assertIn("tiny_live mode requires --request-tiny-live", payload["blockers"])

    def test_tiny_live_config_change_does_not_bypass_global_gates(self) -> None:
        payload = self._command(
            action="request-tiny-live-mode",
            lane_key=LANE_KEY,
            mode="tiny_live",
            request_tiny_live=True,
            apply=True,
            confirm_lane_change=CONFIRM_LANE_CHANGE_PHRASE,
            global_gate={"status": "FIRST_LIVE_BLOCKED", "execution_enabled_by_gate": False},
        )

        self.assertEqual(LANE_COMMAND_APPLIED, payload["status"])
        self.assertEqual("tiny_live", self._read_config()["lanes"][0]["mode"])
        self.assertEqual("LANE_BLOCKED", payload["lane_status_after_change"]["status"])
        self.assertIn(
            "global first-live activation gate is not FIRST_LIVE_ACTIVATION_READY",
            payload["lane_status_after_change"]["blockers"],
        )

    def test_risk_limits_are_preserved_on_mode_change(self) -> None:
        payload = self._command(
            action="enable-armed-dry-run",
            lane_key=LANE_KEY,
            apply=True,
            confirm_lane_change=CONFIRM_LANE_CHANGE_PHRASE,
        )

        self.assertEqual(LANE_COMMAND_APPLIED, payload["status"])
        self.assertEqual(
            {
                "max_daily_trades": 1,
                "max_daily_loss_pct": 0.25,
                "cooldown_after_loss_minutes": 120,
                "require_protective_orders": True,
            },
            payload["lane_status_after_change"]["risk_limits"],
        )

    def test_audit_ledger_is_written_on_apply(self) -> None:
        payload = self._command(
            action="disable-lane",
            lane_key=LANE_KEY,
            apply=True,
            confirm_lane_change=CONFIRM_LANE_CHANGE_PHRASE,
        )
        ledger = self.log_dir / "lane_control_commands.ndjson"
        record = json.loads(ledger.read_text(encoding="utf-8").strip())

        self.assertTrue(payload["ledger_written"])
        self.assertEqual("LANE_CONTROL_COMMAND", record["event_type"])
        self.assertEqual(LANE_KEY, record["lane_key"])
        self.assertEqual("disabled", record["resulting_mode"])
        self.assertTrue(record["config_written"])

    def test_safety_flags_are_always_false(self) -> None:
        payload = self._command(
            action="set-mode",
            lane_key=LANE_KEY,
            mode="armed_dry_run",
            apply=True,
            confirm_lane_change=CONFIRM_LANE_CHANGE_PHRASE,
        )

        self.assertEqual(
            {
                "order_placed": False,
                "real_order_placed": False,
                "execution_attempted": False,
                "order_payload_created": False,
                "network_allowed": False,
                "secrets_shown": False,
                "env_mutated": False,
                "global_live_flags_changed": False,
            },
            payload["safety"],
        )

    def test_cli_mode_exists_and_returns_compact_status(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                str(self.log_dir),
                "lane-control-command",
                "--action",
                "list",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        payload = json.loads(result.stdout)
        self.assertEqual(LANE_COMMAND_LIST, payload["status"])
        self.assertNotIn("recommendations", result.stdout)
        self.assertLess(len(result.stdout), 8000)

    def test_no_secrets_or_confirmation_phrase_are_exposed(self) -> None:
        payload = self._command(
            action="set-mode",
            lane_key=LANE_KEY,
            mode="armed_dry_run",
            apply=True,
            confirm_lane_change=CONFIRM_LANE_CHANGE_PHRASE,
        )
        rendered = json.dumps(payload)

        self.assertNotIn(CONFIRM_LANE_CHANGE_PHRASE, rendered)
        self.assertNotIn("api_key", rendered.lower())
        self.assertNotIn("token", rendered.lower())
        self.assertNotIn("wrong", rendered.lower())
        self.assertFalse(payload["safety"]["secrets_shown"])

    def _command(self, **kwargs: object) -> dict[str, object]:
        return apply_lane_command(
            config_path=self.config_path,
            log_dir=self.log_dir,
            live_eligibility_matrix=self.matrix,
            global_gate=kwargs.pop("global_gate", {"status": "FIRST_LIVE_BLOCKED", "execution_enabled_by_gate": False}),
            **kwargs,
        )

    def _write_config(self, payload: dict[str, object]) -> None:
        self.config_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def _read_config(self) -> dict[str, object]:
        return json.loads(self.config_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
