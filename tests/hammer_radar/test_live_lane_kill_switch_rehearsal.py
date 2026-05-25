from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.live_lane_kill_switch_rehearsal import (
    CONFIRM_REHEARSAL_RECORD_PHRASE,
    EVENT_TYPE,
    KILL_SWITCH_REHEARSAL_READY,
    KILL_SWITCH_REHEARSAL_REJECTED,
    LEDGER_FILENAME,
    append_live_lane_kill_switch_rehearsal_record,
    build_live_lane_kill_switch_rehearsal,
    build_live_lane_kill_switch_rehearsal_cli_payload,
    load_live_lane_kill_switch_rehearsal_records,
    simulate_global_kill_switch_block,
    simulate_lane_disable,
    simulate_lane_mode_rollback,
    simulate_scheduler_respects_killed_lane,
    simulate_tiny_live_promotion_reversal,
)
from src.app.hammer_radar.operator.strategy_performance import ELIGIBLE_FOR_FUTURE_TINY_LIVE

LANE_KEY = "BTCUSDT|13m|long|ladder_close_50_618"


class LiveLaneKillSwitchRehearsalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.log_dir = self.root / "logs"
        self.config_path = self.root / "lane_controls.json"
        self.now = datetime(2026, 5, 25, 18, 0, tzinfo=UTC)
        self._write_config("armed_dry_run")
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
                    "blockers": [],
                }
            ]
        }

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_preview_writes_no_rehearsal_record(self) -> None:
        payload = self._rehearsal()

        self.assertEqual(KILL_SWITCH_REHEARSAL_READY, payload["status"])
        self.assertFalse((self.log_dir / LEDGER_FILENAME).exists())
        self.assertFalse(payload["safety"]["config_written"])
        self.assertFalse(payload["safety"]["env_mutated"])

    def test_wrong_confirmation_rejects_recording(self) -> None:
        payload = build_live_lane_kill_switch_rehearsal_cli_payload(
            log_dir=self.log_dir,
            lane_key=LANE_KEY,
            record_rehearsal=True,
            confirm_rehearsal_record="wrong",
            config_path=self.config_path,
        )

        self.assertEqual(KILL_SWITCH_REHEARSAL_REJECTED, payload["status"])
        self.assertFalse(payload["confirmation_valid"])
        self.assertFalse(payload["ledger_written"])
        self.assertFalse((self.log_dir / LEDGER_FILENAME).exists())

    def test_exact_confirmation_records_rehearsal_only(self) -> None:
        payload = build_live_lane_kill_switch_rehearsal_cli_payload(
            log_dir=self.log_dir,
            lane_key=LANE_KEY,
            record_rehearsal=True,
            confirm_rehearsal_record=CONFIRM_REHEARSAL_RECORD_PHRASE,
            config_path=self.config_path,
        )
        records = load_live_lane_kill_switch_rehearsal_records(log_dir=self.log_dir, limit=0)

        self.assertEqual(KILL_SWITCH_REHEARSAL_READY, payload["status"])
        self.assertTrue(payload["ledger_written"])
        self.assertEqual(1, len(records))
        self.assertEqual(EVENT_TYPE, records[0]["event_type"])
        self.assertEqual(LANE_KEY, records[0]["lane_key"])
        self.assertFalse(records[0]["safety"]["order_placed"])
        self.assertFalse(records[0]["safety"]["real_order_placed"])
        self.assertFalse(records[0]["safety"]["execution_attempted"])
        self.assertFalse(records[0]["safety"]["order_payload_created"])
        self.assertFalse(records[0]["safety"]["network_allowed"])
        self.assertFalse(records[0]["safety"]["secrets_shown"])
        self.assertFalse(records[0]["safety"]["config_written"])
        self.assertFalse(records[0]["safety"]["env_mutated"])

    def test_lane_disable_simulation_blocks_live_intent(self) -> None:
        payload = simulate_lane_disable(
            lane_key=LANE_KEY,
            controls=self._controls(),
            now=self.now,
            live_eligibility_matrix=self.matrix,
            log_dir=self.log_dir,
        )

        self.assertTrue(payload["live_intent_blocked"])
        self.assertIn(payload["autonomy_decision"], {"BLOCKED", "IGNORE"})
        self.assertFalse(payload["safety"]["config_written"])

    def test_global_kill_switch_simulation_blocks_live_intent(self) -> None:
        payload = simulate_global_kill_switch_block(
            lane_key=LANE_KEY,
            controls=self._controls(),
            now=self.now,
            live_eligibility_matrix=self.matrix,
            log_dir=self.log_dir,
        )

        self.assertTrue(payload["live_intent_blocked"])
        self.assertIn("global kill switch active", payload["blockers"])
        self.assertTrue(payload["paper_live_separation_intact"])

    def test_rollback_simulation_blocks_tiny_live_intent(self) -> None:
        payload = simulate_lane_mode_rollback(
            lane_key=LANE_KEY,
            controls=self._controls(),
            now=self.now,
            live_eligibility_matrix=self.matrix,
            log_dir=self.log_dir,
        )

        self.assertTrue(payload["tiny_live_intent_blocked"])
        self.assertEqual("TINY_LIVE_EXECUTION_BLOCKED", payload["r126_status_after_rollback"])
        self.assertNotEqual("TINY_LIVE_GATE_REVIEW", payload["autonomy_decision"])

    def test_scheduler_respects_disabled_lane(self) -> None:
        payload = simulate_scheduler_respects_killed_lane(
            lane_key=LANE_KEY,
            controls=self._controls(),
            now=self.now,
            live_eligibility_matrix=self.matrix,
            log_dir=self.log_dir,
        )

        self.assertTrue(payload["scheduler_respects_disabled_lane"])
        self.assertIn(payload["autonomy_decision"], {"BLOCKED", "IGNORE"})

    def test_paper_proof_gap_includes_r129_command(self) -> None:
        payload = self._rehearsal()

        self.assertIn("autonomous-paper-lane-executor-integration", payload["safe_command_pack"]["paper_proof_preview"])
        self.assertIn("I CONFIRM AUTONOMOUS PAPER LANE INTEGRATION ONLY", payload["safe_command_pack"]["paper_proof_confirmed_record_command"])

    def test_tiny_live_promotion_gap_includes_r124_and_r130_command_hints(self) -> None:
        payload = self._rehearsal()

        self.assertIn("lane-control-command", payload["safe_command_pack"]["tiny_live_mode_preview"])
        self.assertIn("first-tiny-live-autonomous-lane-authorization", payload["safe_command_pack"]["tiny_live_authorization_preview"])
        reversal = simulate_tiny_live_promotion_reversal(
            lane_key=LANE_KEY,
            controls=self._controls(),
            now=self.now,
            live_eligibility_matrix=self.matrix,
            log_dir=self.log_dir,
        )
        self.assertTrue(reversal["tiny_live_intent_blocked"])

    def test_safety_flags_are_always_false_and_separation_true(self) -> None:
        payload = self._rehearsal()

        self.assertEqual(
            {
                "order_placed": False,
                "real_order_placed": False,
                "execution_attempted": False,
                "order_payload_created": False,
                "network_allowed": False,
                "secrets_shown": False,
                "paper_live_separation_intact": True,
                "env_mutated": False,
                "config_written": False,
                "global_live_flags_changed": False,
            },
            payload["safety"],
        )

    def test_ledger_append_only(self) -> None:
        first = self._rehearsal()
        second = self._rehearsal()
        append_live_lane_kill_switch_rehearsal_record(first, log_dir=self.log_dir)
        append_live_lane_kill_switch_rehearsal_record(second, log_dir=self.log_dir)
        records = load_live_lane_kill_switch_rehearsal_records(log_dir=self.log_dir, limit=0)

        self.assertEqual(2, len(records))
        self.assertNotEqual(records[0]["rehearsal_id"], records[1]["rehearsal_id"])

    def test_cli_mode_exists_and_returns_compact_status(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                str(self.log_dir),
                "live-lane-kill-switch-rehearsal",
                "--lane-key",
                LANE_KEY,
            ],
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": "."},
        )

        payload = json.loads(result.stdout)
        self.assertIn(payload["status"], {KILL_SWITCH_REHEARSAL_READY, "KILL_SWITCH_REHEARSAL_BLOCKED"})
        self.assertIn("kill_switch_verdict", payload)
        self.assertIn("safe_command_pack", payload)
        self.assertLess(len(result.stdout), 30000)

    def test_no_binance_order_payload_or_network_calls_occur(self) -> None:
        from src.app.hammer_radar.execution import binance_futures_connector

        with (
            patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
            patch.object(binance_futures_connector, "preview_payload") as preview_payload,
            patch.object(binance_futures_connector, "protective_preview") as protective_preview,
            patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        ):
            payload = self._rehearsal()

        execute_live_order.assert_not_called()
        preview_payload.assert_not_called()
        protective_preview.assert_not_called()
        submit_test_order.assert_not_called()
        self.assertFalse(payload["safety"]["order_payload_created"])
        self.assertFalse(payload["safety"]["network_allowed"])
        self.assertFalse(payload["safety"]["execution_attempted"])

    def _rehearsal(self) -> dict[str, object]:
        return build_live_lane_kill_switch_rehearsal(
            log_dir=self.log_dir,
            lane_key=LANE_KEY,
            config_path=self.config_path,
            now=self.now,
            live_eligibility_matrix=self.matrix,
        )

    def _controls(self) -> dict[str, object]:
        from src.app.hammer_radar.operator.lane_control import load_lane_controls

        return load_lane_controls(self.config_path)

    def _write_config(self, mode: str) -> None:
        self.config_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "default_mode": "disabled",
                    "notes": ["test"],
                    "lanes": [
                        {
                            "symbol": "BTCUSDT",
                            "timeframe": "13m",
                            "direction": "long",
                            "entry_mode": "ladder_close_50_618",
                            "mode": mode,
                            "max_daily_trades": 1,
                            "max_daily_loss_pct": 0.25,
                            "freshness_seconds": 120,
                            "cooldown_after_loss_minutes": 120,
                            "require_protective_orders": True,
                        }
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
