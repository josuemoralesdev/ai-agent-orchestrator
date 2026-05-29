import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from src.app.hammer_radar.operator.apply_tiny_live_lane_mode_recheck import (
    APPLY_TINY_LIVE_LANE_MODE_ON_MAIN,
    CONFIRM_TINY_LIVE_LANE_MODE_RECHECK_RECORDING_PHRASE,
    SAFETY,
    TINY_LIVE_LANE_MODE_RECHECK_PREVIEW,
    TINY_LIVE_LANE_MODE_RECHECK_RECORDED,
    TINY_LIVE_LANE_MODE_RECHECK_REJECTED,
    build_default_tiny_live_lane_targets,
    build_tiny_live_lane_mode_recheck_status,
    load_tiny_live_lane_mode_recheck_records,
)
from src.app.hammer_radar.operator.lane_command_interface import CONFIRM_LANE_CHANGE_PHRASE
from src.app.hammer_radar.operator.strategy_performance import ELIGIBLE_FOR_FUTURE_TINY_LIVE


TARGET_13M = "BTCUSDT|13m|long|ladder_close_50_618"
TARGET_44M = "BTCUSDT|44m|long|ladder_close_50_618"


def _write_lane_config(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "default_mode": "disabled",
                "lanes": [
                    {
                        "symbol": "BTCUSDT",
                        "timeframe": "13m",
                        "direction": "long",
                        "entry_mode": "ladder_close_50_618",
                        "mode": "armed_dry_run",
                        "max_daily_trades": 1,
                        "max_daily_loss_pct": 0.25,
                        "freshness_seconds": 120,
                        "cooldown_after_loss_minutes": 120,
                        "require_protective_orders": True,
                    },
                    {
                        "symbol": "BTCUSDT",
                        "timeframe": "44m",
                        "direction": "long",
                        "entry_mode": "ladder_close_50_618",
                        "mode": "paper",
                        "max_daily_trades": 1,
                        "max_daily_loss_pct": 0.25,
                        "freshness_seconds": 300,
                        "cooldown_after_loss_minutes": 180,
                        "require_protective_orders": True,
                    },
                ],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _eligibility_matrix() -> dict:
    return {
        "recommendations": [
            {
                "symbol": "BTCUSDT",
                "timeframe": "13m",
                "direction": "long",
                "entry_mode": "ladder_close_50_618",
                "recommendation": ELIGIBLE_FOR_FUTURE_TINY_LIVE,
            },
            {
                "symbol": "BTCUSDT",
                "timeframe": "44m",
                "direction": "long",
                "entry_mode": "ladder_close_50_618",
                "recommendation": ELIGIBLE_FOR_FUTURE_TINY_LIVE,
            },
        ]
    }


class ApplyTinyLiveLaneModeRecheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.log_dir = self.root / "logs"
        self.config_path = self.root / "lane_controls.json"
        self.log_dir.mkdir()
        _write_lane_config(self.config_path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _build(self, **overrides):
        kwargs = {
            "log_dir": self.log_dir,
            "all_target_lanes": True,
            "config_path": self.config_path,
            "live_eligibility_matrix": _eligibility_matrix(),
        }
        kwargs.update(overrides)
        return build_tiny_live_lane_mode_recheck_status(**kwargs)

    def test_default_target_lanes_are_13m_and_44m_long_ladder(self):
        self.assertEqual([TARGET_13M, TARGET_44M], build_default_tiny_live_lane_targets())

    def test_preview_writes_no_recheck_and_detects_current_modes(self):
        payload = self._build(
            include_apply_commands=True,
            include_post_apply_recheck_commands=True,
        )
        self.assertEqual(TINY_LIVE_LANE_MODE_RECHECK_PREVIEW, payload["status"])
        self.assertFalse(payload["record_recheck_requested"])
        self.assertFalse(payload["confirmation_valid"])
        self.assertFalse(payload["recheck_recorded"])
        self.assertIsNone(payload["recheck_id"])
        self.assertEqual("armed_dry_run", payload["current_lane_modes"][TARGET_13M]["current_mode"])
        self.assertEqual("paper", payload["current_lane_modes"][TARGET_44M]["current_mode"])
        self.assertTrue(payload["current_lane_modes"][TARGET_13M]["needs_apply"])
        self.assertTrue(payload["current_lane_modes"][TARGET_44M]["needs_apply"])
        self.assertTrue(payload["current_lane_modes"][TARGET_13M]["eligible_future_tiny_live"])
        self.assertEqual([], load_tiny_live_lane_mode_recheck_records(log_dir=self.log_dir))

    def test_wrong_confirmation_rejects_record(self):
        payload = self._build(record_recheck=True, confirm_recheck="wrong")
        self.assertEqual(TINY_LIVE_LANE_MODE_RECHECK_REJECTED, payload["status"])
        self.assertFalse(payload["confirmation_valid"])
        self.assertFalse(payload["recheck_recorded"])
        self.assertEqual([], load_tiny_live_lane_mode_recheck_records(log_dir=self.log_dir))

    def test_exact_confirmation_records_recheck_only_append_only(self):
        first = self._build(
            record_recheck=True,
            confirm_recheck=CONFIRM_TINY_LIVE_LANE_MODE_RECHECK_RECORDING_PHRASE,
            include_apply_commands=True,
            include_post_apply_recheck_commands=True,
        )
        second = self._build(
            record_recheck=True,
            confirm_recheck=CONFIRM_TINY_LIVE_LANE_MODE_RECHECK_RECORDING_PHRASE,
        )
        self.assertEqual(TINY_LIVE_LANE_MODE_RECHECK_RECORDED, first["status"])
        self.assertEqual(TINY_LIVE_LANE_MODE_RECHECK_RECORDED, second["status"])
        self.assertTrue(first["recheck_recorded"])
        records = load_tiny_live_lane_mode_recheck_records(log_dir=self.log_dir, limit=0)
        self.assertEqual(2, len(records))
        self.assertEqual({TARGET_13M, TARGET_44M}, set(records[0]["target_lanes"]))
        self.assertFalse(records[0]["safety"]["config_written"])
        self.assertFalse(records[0]["safety"]["order_placed"])

    def test_includes_apply_commands_but_does_not_execute_them(self):
        payload = self._build(include_apply_commands=True)
        commands = "\n".join(payload["apply_commands"])
        self.assertIn("lane-control-command", commands)
        self.assertIn("--apply", commands)
        self.assertIn(CONFIRM_LANE_CHANGE_PHRASE, commands)
        self.assertIn(TARGET_13M, commands)
        self.assertIn(TARGET_44M, commands)
        stored = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual("armed_dry_run", stored["lanes"][0]["mode"])
        self.assertEqual("paper", stored["lanes"][1]["mode"])
        self.assertFalse(payload["safety"]["config_written"])

    def test_includes_post_apply_recheck_commands_without_unsafe_commands(self):
        payload = self._build(include_post_apply_recheck_commands=True)
        commands = "\n".join(payload["post_apply_recheck_commands"])
        self.assertIn("lane-control-status", commands)
        self.assertIn("first-tiny-live-lane-execution-gate", commands)
        self.assertIn("post-bridge-watcher-proof-capture-recheck", commands)
        self.assertIn("binance-readonly-status", commands)
        self.assertIn("live-safety", commands)
        self.assertIn("fresh-candidate-paper-proof-capture-loop", commands)
        forbidden = ["live-connector-submit", "kill switch disable", "BINANCE_LIVE_TRADING_ENABLED=true"]
        for item in forbidden:
            self.assertNotIn(item, commands)

    def test_expected_after_apply_blocks_execution_and_orders(self):
        payload = self._build()
        self.assertFalse(payload["expected_after_apply"]["live_execution_enabled"])
        self.assertFalse(payload["expected_after_apply"]["orders_allowed"])
        self.assertTrue(payload["expected_after_apply"]["global_kill_switch_remains_authoritative"])
        self.assertEqual(APPLY_TINY_LIVE_LANE_MODE_ON_MAIN, payload["next_operator_move"])

    def test_safety_flags_preserve_no_mutation_no_payload_no_network(self):
        payload = self._build()
        for key, expected in SAFETY.items():
            self.assertEqual(expected, payload["safety"][key], key)
        self.assertFalse(payload["safety"]["binance_order_endpoint_called"])
        self.assertFalse(payload["safety"]["binance_test_order_endpoint_called"])
        self.assertFalse(payload["safety"]["protective_order_endpoint_called"])
        self.assertFalse(payload["safety"]["signed_request_created"])
        self.assertFalse(payload["safety"]["network_allowed"])
        self.assertFalse(payload["safety"]["env_mutated"])
        self.assertFalse(payload["safety"]["global_live_flags_changed"])

    def test_cli_exists(self):
        result = subprocess.run(
            [
                ".venv/bin/python",
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                str(self.log_dir),
                "apply-tiny-live-lane-mode-recheck",
                "--all-target-lanes",
            ],
            cwd=Path(__file__).resolve().parents[2],
            env={"PYTHONPATH": "."},
            text=True,
            capture_output=True,
            check=True,
        )
        payload = json.loads(result.stdout)
        self.assertIn(payload["status"], {TINY_LIVE_LANE_MODE_RECHECK_PREVIEW, "TINY_LIVE_LANE_MODE_RECHECK_READY"})
        self.assertEqual([TARGET_13M, TARGET_44M], payload["target_lanes"])


if __name__ == "__main__":
    unittest.main()
