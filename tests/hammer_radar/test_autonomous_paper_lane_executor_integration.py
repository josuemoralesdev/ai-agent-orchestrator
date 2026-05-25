from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.autonomous_paper_lane_execution import (
    ARMED_DRY_RUN_ENTRY_RECORDED,
    AUTONOMOUS_PAPER_LANE_EXECUTIONS_LEDGER,
    PAPER_ENTRY_RECORDED,
    PAPER_SHADOW_FOR_TINY_LIVE,
    append_paper_lane_execution,
    load_paper_lane_executions,
)
from src.app.hammer_radar.operator.autonomous_paper_lane_executor_integration import (
    AUTONOMOUS_PAPER_LANE_EXECUTOR_INTEGRATIONS_LEDGER,
    CONFIRM_PAPER_INTEGRATION_PHRASE,
    PAPER_EXECUTOR_INTEGRATION_PARTIAL,
    PAPER_EXECUTOR_INTEGRATION_PREVIEW,
    PAPER_EXECUTOR_INTEGRATION_RECORDED,
    PAPER_EXECUTOR_INTEGRATION_REJECTED,
    build_paper_execution_from_autonomy_decision,
    load_paper_executor_integration_records,
    run_autonomous_paper_lane_executor_once,
    select_paper_executable_decisions,
)
from src.app.hammer_radar.operator.lane_autonomy_control_loop import (
    ARMED_DRY_RUN_INTENT,
    BLOCKED,
    IGNORE,
    PAPER_ENTRY_INTENT,
    TINY_LIVE_GATE_REVIEW,
)
from src.app.hammer_radar.operator.lane_autonomy_scheduler import LANE_AUTONOMY_SCHEDULER_TICKS_LEDGER
from src.app.hammer_radar.operator.strategy_performance import ELIGIBLE_FOR_FUTURE_TINY_LIVE

LANE_44M = "BTCUSDT|44m|long|ladder_close_50_618"
LANE_13M = "BTCUSDT|13m|long|ladder_close_50_618"
LANE_8M = "BTCUSDT|8m|long|ladder_close_50_618"


class AutonomousPaperLaneExecutorIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.log_dir = self.root / "logs"
        self.config_path = self.root / "lane_controls.json"
        self.now = datetime(2026, 5, 25, 16, 0, tzinfo=UTC)
        self._write_config(
            [
                self._lane("44m", "paper", max_daily_trades=3),
                self._lane("13m", "armed_dry_run", max_daily_trades=3),
                self._lane("8m", "tiny_live", max_daily_trades=3),
            ]
        )
        self.matrix = {
            "recommendations": [
                self._eligibility("13m", ELIGIBLE_FOR_FUTURE_TINY_LIVE),
                self._eligibility("44m", ELIGIBLE_FOR_FUTURE_TINY_LIVE),
                self._eligibility("8m", ELIGIBLE_FOR_FUTURE_TINY_LIVE),
            ]
        }
        self.global_blocked = {"status": "FIRST_LIVE_BLOCKED", "execution_enabled_by_gate": False}
        self.global_ready = {"status": "FIRST_LIVE_ACTIVATION_READY", "execution_enabled_by_gate": True}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_preview_mode_writes_no_integration_or_paper_records(self) -> None:
        payload = self._run(candidates=[self._candidate("44m", seconds_old=60)])

        self.assertEqual(PAPER_EXECUTOR_INTEGRATION_PREVIEW, payload["status"])
        self.assertEqual(1, payload["paper_eligible_decisions_count"])
        self.assertEqual(0, payload["paper_execution_records_created"])
        self.assertFalse((self.log_dir / AUTONOMOUS_PAPER_LANE_EXECUTOR_INTEGRATIONS_LEDGER).exists())
        self.assertFalse((self.log_dir / AUTONOMOUS_PAPER_LANE_EXECUTIONS_LEDGER).exists())

    def test_wrong_confirmation_rejects_recording(self) -> None:
        payload = self._run(
            record_paper=True,
            confirm_paper_integration="wrong",
            candidates=[self._candidate("44m", seconds_old=60)],
        )

        self.assertEqual(PAPER_EXECUTOR_INTEGRATION_REJECTED, payload["status"])
        self.assertFalse(payload["confirmation_valid"])
        self.assertEqual("missing or invalid paper integration confirmation", payload["rejection_reason"])
        self.assertFalse((self.log_dir / AUTONOMOUS_PAPER_LANE_EXECUTOR_INTEGRATIONS_LEDGER).exists())
        self.assertFalse((self.log_dir / AUTONOMOUS_PAPER_LANE_EXECUTIONS_LEDGER).exists())

    def test_exact_confirmation_records_integration_and_paper_execution_only(self) -> None:
        payload = self._run(
            record_paper=True,
            confirm_paper_integration=CONFIRM_PAPER_INTEGRATION_PHRASE,
            candidates=[self._candidate("44m", seconds_old=60, candidate_id="paper")],
        )
        paper_records = load_paper_lane_executions(log_dir=self.log_dir)
        integration_records = load_paper_executor_integration_records(log_dir=self.log_dir)

        self.assertEqual(PAPER_EXECUTOR_INTEGRATION_RECORDED, payload["status"])
        self.assertTrue(payload["integration_recorded"])
        self.assertEqual(1, payload["paper_execution_records_created"])
        self.assertEqual(1, len(paper_records))
        self.assertEqual(1, len(integration_records))
        self.assertEqual(PAPER_ENTRY_RECORDED, paper_records[0]["paper_action"])
        self.assertEqual("paper", paper_records[0]["candidate_id"])
        self.assertEqual(self._safe(), paper_records[0]["safety"])
        self.assertEqual(self._safe(), integration_records[0]["safety"])

    def test_paper_entry_intent_creates_paper_execution_record(self) -> None:
        payload = self._run(candidates=[self._candidate("44m", seconds_old=60)])

        self.assertEqual(PAPER_ENTRY_INTENT, payload["candidate_decisions"][0]["autonomy_decision"])
        self.assertEqual(1, payload["paper_eligible_decisions_count"])

    def test_armed_dry_run_intent_creates_armed_dry_run_paper_execution_record(self) -> None:
        payload = self._run(
            record_paper=True,
            confirm_paper_integration=CONFIRM_PAPER_INTEGRATION_PHRASE,
            candidates=[self._candidate("13m", seconds_old=60)],
        )
        records = load_paper_lane_executions(log_dir=self.log_dir)

        self.assertEqual(PAPER_EXECUTOR_INTEGRATION_RECORDED, payload["status"])
        self.assertEqual(ARMED_DRY_RUN_ENTRY_RECORDED, records[0]["paper_action"])

    def test_tiny_live_gate_review_creates_paper_shadow_only(self) -> None:
        payload = self._run(
            record_paper=True,
            confirm_paper_integration=CONFIRM_PAPER_INTEGRATION_PHRASE,
            candidates=[self._candidate("8m", seconds_old=30)],
            global_gate=self.global_ready,
        )
        records = load_paper_lane_executions(log_dir=self.log_dir)

        self.assertEqual(PAPER_EXECUTOR_INTEGRATION_RECORDED, payload["status"])
        self.assertEqual(TINY_LIVE_GATE_REVIEW, payload["candidate_decisions"][0]["autonomy_decision"])
        self.assertEqual(PAPER_SHADOW_FOR_TINY_LIVE, records[0]["paper_action"])
        self.assertTrue(records[0]["paper_shadow_only"])
        self.assertFalse(records[0]["safety"]["real_order_placed"])
        self.assertFalse(records[0]["safety"]["execution_attempted"])

    def test_blocked_and_ignore_decisions_do_not_create_paper_executions(self) -> None:
        selected = select_paper_executable_decisions(
            [
                {"decision_id": "blocked", "autonomy_decision": BLOCKED, "lane_key": LANE_44M, "blockers": ["blocked"]},
                {"decision_id": "ignore", "autonomy_decision": IGNORE, "lane_key": LANE_44M, "blockers": []},
            ]
        )

        self.assertEqual([], selected["eligible_decisions"])
        self.assertEqual(2, len(selected["blocked_decisions"]))

    def test_max_daily_trades_blocks_additional_records(self) -> None:
        self._write_config([self._lane("44m", "paper", max_daily_trades=1)])
        append_paper_lane_execution(
            {
                "event_type": "AUTONOMOUS_PAPER_LANE_EXECUTION",
                "paper_execution_id": "existing",
                "recorded_at_utc": self.now.isoformat(),
                "lane_key": LANE_44M,
                "paper_action": PAPER_ENTRY_RECORDED,
                "safety": self._safe(),
            },
            log_dir=self.log_dir,
        )
        payload = self._run(
            record_paper=True,
            confirm_paper_integration=CONFIRM_PAPER_INTEGRATION_PHRASE,
            candidates=[self._candidate("44m", seconds_old=60)],
        )

        self.assertEqual(PAPER_EXECUTOR_INTEGRATION_REJECTED, payload["status"])
        self.assertIn("lane max_daily_trades exceeded", payload["rejection_reason"])
        self.assertEqual(1, len(load_paper_lane_executions(log_dir=self.log_dir)))

    def test_cooldown_blocks_records(self) -> None:
        append_paper_lane_execution(
            {
                "event_type": "AUTONOMOUS_PAPER_LANE_EXECUTION",
                "paper_execution_id": "loss",
                "recorded_at_utc": (self.now - timedelta(minutes=10)).isoformat(),
                "lane_key": LANE_44M,
                "paper_action": PAPER_ENTRY_RECORDED,
                "pnl_pct": -0.1,
                "safety": self._safe(),
            },
            log_dir=self.log_dir,
        )
        payload = self._run(
            record_paper=True,
            confirm_paper_integration=CONFIRM_PAPER_INTEGRATION_PHRASE,
            candidates=[self._candidate("44m", seconds_old=60)],
        )

        self.assertEqual(PAPER_EXECUTOR_INTEGRATION_REJECTED, payload["status"])
        self.assertIn("lane cooldown_after_loss_minutes is active", payload["rejection_reason"])
        self.assertEqual(1, len(load_paper_lane_executions(log_dir=self.log_dir)))

    def test_safety_flags_are_always_false_and_separation_true_in_safe_flow(self) -> None:
        payload = self._run(candidates=[self._candidate("44m", seconds_old=60)])
        record = build_paper_execution_from_autonomy_decision(
            {
                "autonomy_decision": PAPER_ENTRY_INTENT,
                "candidate_id": "safe",
                "lane_key": LANE_44M,
                "lane_mode": "paper",
                "route_status": "ROUTED_TO_LANE",
                "blockers": [],
            },
            lane=self._lane("44m", "paper", max_daily_trades=3),
            existing_records=[],
            now=self.now,
        )

        self.assertEqual(self._safe(), payload["safety"])
        self.assertEqual(self._safe(), record["safety"])

    def test_integration_ledger_append_only(self) -> None:
        first = self._run(
            record_paper=True,
            confirm_paper_integration=CONFIRM_PAPER_INTEGRATION_PHRASE,
            candidates=[self._candidate("44m", seconds_old=60, candidate_id="first")],
        )
        second = self._run(
            record_paper=True,
            confirm_paper_integration=CONFIRM_PAPER_INTEGRATION_PHRASE,
            candidates=[self._candidate("13m", seconds_old=60, candidate_id="second")],
        )
        integrations = load_paper_executor_integration_records(log_dir=self.log_dir, limit=0)

        self.assertEqual(PAPER_EXECUTOR_INTEGRATION_RECORDED, first["status"])
        self.assertEqual(PAPER_EXECUTOR_INTEGRATION_RECORDED, second["status"])
        self.assertEqual(2, len(integrations))
        self.assertEqual([first["integration_id"], second["integration_id"]], [row["integration_id"] for row in integrations])

    def test_cli_mode_exists_and_returns_compact_status(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                str(self.log_dir),
                "autonomous-paper-lane-executor-integration",
            ],
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": "."},
        )

        payload = json.loads(result.stdout)
        self.assertEqual(PAPER_EXECUTOR_INTEGRATION_PREVIEW, payload["status"])
        self.assertIn("paper_eligible_decisions_count", payload)
        self.assertNotIn("recommendations", result.stdout)
        self.assertLess(len(result.stdout), 10000)

    def test_no_binance_order_payload_or_network_calls_occur(self) -> None:
        from src.app.hammer_radar.execution import binance_futures_connector

        with (
            patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
            patch.object(binance_futures_connector, "preview_payload") as preview_payload,
            patch.object(binance_futures_connector, "protective_preview") as protective_preview,
            patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        ):
            payload = self._run(
                record_paper=True,
                record_scheduler_tick=True,
                record_decisions=True,
                confirm_paper_integration=CONFIRM_PAPER_INTEGRATION_PHRASE,
                candidates=[self._candidate("44m", seconds_old=60)],
            )

        execute_live_order.assert_not_called()
        preview_payload.assert_not_called()
        protective_preview.assert_not_called()
        submit_test_order.assert_not_called()
        rendered = json.dumps(payload).lower()
        self.assertNotIn("binance_futures_connector", rendered)
        self.assertFalse(payload["safety"]["order_payload_created"])
        self.assertFalse(payload["safety"]["network_allowed"])
        self.assertFalse(payload["safety"]["execution_attempted"])
        self.assertTrue((self.log_dir / LANE_AUTONOMY_SCHEDULER_TICKS_LEDGER).exists())

    def _run(self, **kwargs: object) -> dict[str, object]:
        return run_autonomous_paper_lane_executor_once(
            log_dir=self.log_dir,
            config_path=self.config_path,
            now=self.now,
            live_eligibility_matrix=self.matrix,
            global_gate=kwargs.pop("global_gate", self.global_blocked),
            **kwargs,
        )

    def _candidate(
        self,
        timeframe: str,
        *,
        seconds_old: int,
        candidate_id: str | None = None,
    ) -> dict[str, object]:
        return {
            "candidate_id": candidate_id or f"BTCUSDT-{timeframe}-{seconds_old}",
            "symbol": "BTCUSDT",
            "timeframe": timeframe,
            "direction": "long",
            "entry_mode": "ladder_close_50_618",
            "generated_at": (self.now - timedelta(seconds=seconds_old)).isoformat(),
            "entry": 100.0,
            "stop": 99.0,
            "take_profit": 102.0,
            "score": 101,
        }

    def _write_config(self, lanes: list[dict[str, object]]) -> None:
        self.config_path.write_text(
            json.dumps({"schema_version": "1.0", "default_mode": "disabled", "notes": ["test"], "lanes": lanes}, indent=2) + "\n",
            encoding="utf-8",
        )

    def _lane(self, timeframe: str, mode: str, *, max_daily_trades: int) -> dict[str, object]:
        return {
            "symbol": "BTCUSDT",
            "timeframe": timeframe,
            "direction": "long",
            "entry_mode": "ladder_close_50_618",
            "mode": mode,
            "max_daily_trades": max_daily_trades,
            "max_daily_loss_pct": 0.25,
            "freshness_seconds": 300,
            "cooldown_after_loss_minutes": 120,
            "require_protective_orders": True,
        }

    def _eligibility(self, timeframe: str, recommendation: str) -> dict[str, object]:
        return {
            "timeframe": timeframe,
            "direction": "long",
            "entry_mode": "ladder_close_50_618",
            "recommendation": recommendation,
            "sample_count": 50,
            "win_rate_pct": 60.0,
            "avg_pnl_pct": 0.2,
            "total_pnl_pct": 10.0,
            "blockers": [],
        }

    def _safe(self) -> dict[str, bool]:
        return {
            "order_placed": False,
            "real_order_placed": False,
            "execution_attempted": False,
            "order_payload_created": False,
            "network_allowed": False,
            "secrets_shown": False,
            "paper_live_separation_intact": True,
        }


if __name__ == "__main__":
    unittest.main()
