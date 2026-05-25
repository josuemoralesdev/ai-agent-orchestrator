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

from src.app.hammer_radar.operator.lane_autonomy_control_loop import (
    LANE_AUTONOMY_DECISIONS_LEDGER,
    load_lane_autonomy_decisions,
)
from src.app.hammer_radar.operator.lane_autonomy_scheduler import (
    CONFIRM_AUTONOMY_SCHEDULER_RECORDING_PHRASE,
    LANE_AUTONOMY_SCHEDULER_PREVIEW,
    LANE_AUTONOMY_SCHEDULER_REJECTED,
    LANE_AUTONOMY_SCHEDULER_TICK_RECORDED,
    LANE_AUTONOMY_SCHEDULER_TICKS_LEDGER,
    load_scheduler_tick_records,
    run_lane_autonomy_scheduler_once,
)
from src.app.hammer_radar.operator.strategy_performance import ELIGIBLE_FOR_FUTURE_TINY_LIVE

LANE_44M = "BTCUSDT|44m|long|ladder_close_50_618"
LANE_13M = "BTCUSDT|13m|long|ladder_close_50_618"


class LaneAutonomySchedulerTests(unittest.TestCase):
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
            ]
        )
        self.matrix = {
            "recommendations": [
                self._eligibility("13m", ELIGIBLE_FOR_FUTURE_TINY_LIVE),
                self._eligibility("44m", ELIGIBLE_FOR_FUTURE_TINY_LIVE),
            ]
        }
        self.global_gate = {"status": "FIRST_LIVE_BLOCKED", "execution_enabled_by_gate": False}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_default_preview_writes_no_tick_records(self) -> None:
        payload = self._run(candidates=[self._candidate("44m", seconds_old=60)])

        self.assertEqual(LANE_AUTONOMY_SCHEDULER_PREVIEW, payload["status"])
        self.assertFalse(payload["tick_recorded"])
        self.assertEqual(1, payload["decisions_count"])
        self.assertFalse((self.log_dir / LANE_AUTONOMY_SCHEDULER_TICKS_LEDGER).exists())
        self.assertFalse((self.log_dir / LANE_AUTONOMY_DECISIONS_LEDGER).exists())

    def test_wrong_confirmation_rejects_recording(self) -> None:
        payload = self._run(
            record_tick=True,
            confirm_scheduler_record="wrong",
            candidates=[self._candidate("44m", seconds_old=60)],
        )

        self.assertEqual(LANE_AUTONOMY_SCHEDULER_REJECTED, payload["status"])
        self.assertFalse(payload["confirmation_valid"])
        self.assertFalse(payload["tick_recorded"])
        self.assertFalse((self.log_dir / LANE_AUTONOMY_SCHEDULER_TICKS_LEDGER).exists())
        self.assertFalse((self.log_dir / LANE_AUTONOMY_DECISIONS_LEDGER).exists())

    def test_exact_confirmation_records_scheduler_tick_only(self) -> None:
        payload = self._run(
            record_tick=True,
            confirm_scheduler_record=CONFIRM_AUTONOMY_SCHEDULER_RECORDING_PHRASE,
            candidates=[self._candidate("44m", seconds_old=60)],
        )
        ticks = load_scheduler_tick_records(log_dir=self.log_dir, limit=0)

        self.assertEqual(LANE_AUTONOMY_SCHEDULER_TICK_RECORDED, payload["status"])
        self.assertTrue(payload["tick_recorded"])
        self.assertEqual(1, len(ticks))
        self.assertEqual("LANE_AUTONOMY_SCHEDULER_TICK", ticks[0]["event_type"])
        self.assertEqual([], ticks[0]["recorded_decision_ids"])
        self.assertFalse((self.log_dir / LANE_AUTONOMY_DECISIONS_LEDGER).exists())

    def test_record_decisions_records_decision_ids_only_when_confirmed(self) -> None:
        rejected = self._run(
            record_tick=True,
            record_decisions=True,
            confirm_scheduler_record="wrong",
            candidates=[self._candidate("44m", seconds_old=60, candidate_id="bad-confirm")],
        )
        accepted = self._run(
            record_tick=True,
            record_decisions=True,
            confirm_scheduler_record=CONFIRM_AUTONOMY_SCHEDULER_RECORDING_PHRASE,
            candidates=[self._candidate("44m", seconds_old=60, candidate_id="good-confirm")],
        )
        decisions = load_lane_autonomy_decisions(log_dir=self.log_dir)
        ticks = load_scheduler_tick_records(log_dir=self.log_dir, limit=0)

        self.assertEqual(LANE_AUTONOMY_SCHEDULER_REJECTED, rejected["status"])
        self.assertEqual(LANE_AUTONOMY_SCHEDULER_TICK_RECORDED, accepted["status"])
        self.assertEqual(1, len(decisions))
        self.assertEqual("good-confirm", decisions[0]["candidate_id"])
        self.assertEqual([decisions[0]["decision_id"]], accepted["recorded_decision_ids"])
        self.assertEqual([decisions[0]["decision_id"]], ticks[-1]["recorded_decision_ids"])

    def test_scheduler_safety_fields_are_false_and_separation_true(self) -> None:
        payload = self._run(candidates=[self._candidate("44m", seconds_old=60)])

        self.assertEqual(self._safe(), payload["safety"])

    def test_selected_lane_filters_decisions(self) -> None:
        payload = self._run(
            lane_key=LANE_13M,
            candidates=[
                self._candidate("44m", seconds_old=60, candidate_id="not-selected"),
                self._candidate("13m", seconds_old=60, candidate_id="selected"),
            ],
        )

        self.assertEqual([LANE_13M], payload["selected_lane_keys"])
        self.assertEqual({"ARMED_DRY_RUN_INTENT": 1}, payload["decision_summary"]["decision_counts"])
        self.assertEqual({"BTCUSDT|13m|long|ladder_close_50_618": 1}, payload["decision_summary"]["lane_counts"])

    def test_unsupported_lane_rejected(self) -> None:
        payload = self._run(
            record_tick=True,
            lane_key="BTCUSDT|1m|long|ladder_close_50_618",
            confirm_scheduler_record=CONFIRM_AUTONOMY_SCHEDULER_RECORDING_PHRASE,
            candidates=[self._candidate("44m", seconds_old=60)],
        )

        self.assertEqual(LANE_AUTONOMY_SCHEDULER_REJECTED, payload["status"])
        self.assertIn("selected lane not configured", payload["rejection_reason"])
        self.assertFalse((self.log_dir / LANE_AUTONOMY_SCHEDULER_TICKS_LEDGER).exists())

    def test_scheduler_refuses_when_source_safety_violation_exists(self) -> None:
        unsafe = self._candidate("44m", seconds_old=60)
        unsafe["safety"] = {"order_placed": True}
        payload = self._run(
            record_tick=True,
            record_decisions=True,
            confirm_scheduler_record=CONFIRM_AUTONOMY_SCHEDULER_RECORDING_PHRASE,
            candidates=[unsafe],
        )

        self.assertEqual(LANE_AUTONOMY_SCHEDULER_REJECTED, payload["status"])
        self.assertIn("source safety field is unsafe: order_placed=true", payload["rejection_reason"])
        self.assertEqual(self._safe(), payload["safety"])
        self.assertFalse((self.log_dir / LANE_AUTONOMY_SCHEDULER_TICKS_LEDGER).exists())
        self.assertFalse((self.log_dir / LANE_AUTONOMY_DECISIONS_LEDGER).exists())

    def test_scheduler_tick_ledger_append_only(self) -> None:
        first = self._run(
            record_tick=True,
            confirm_scheduler_record=CONFIRM_AUTONOMY_SCHEDULER_RECORDING_PHRASE,
            candidates=[self._candidate("44m", seconds_old=60, candidate_id="first")],
        )
        second = self._run(
            record_tick=True,
            confirm_scheduler_record=CONFIRM_AUTONOMY_SCHEDULER_RECORDING_PHRASE,
            candidates=[self._candidate("44m", seconds_old=60, candidate_id="second")],
        )
        ticks = load_scheduler_tick_records(log_dir=self.log_dir, limit=0)

        self.assertEqual(LANE_AUTONOMY_SCHEDULER_TICK_RECORDED, first["status"])
        self.assertEqual(LANE_AUTONOMY_SCHEDULER_TICK_RECORDED, second["status"])
        self.assertEqual(2, len(ticks))
        self.assertEqual([first["tick_id"], second["tick_id"]], [tick["tick_id"] for tick in ticks])

    def test_cli_mode_exists_and_returns_compact_status(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                str(self.log_dir),
                "lane-autonomy-scheduler",
            ],
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": "."},
        )

        payload = json.loads(result.stdout)
        self.assertEqual(LANE_AUTONOMY_SCHEDULER_PREVIEW, payload["status"])
        self.assertIn("scheduler_recommendation", payload)
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
                record_tick=True,
                record_decisions=True,
                confirm_scheduler_record=CONFIRM_AUTONOMY_SCHEDULER_RECORDING_PHRASE,
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

    def _run(self, **kwargs: object) -> dict[str, object]:
        return run_lane_autonomy_scheduler_once(
            log_dir=self.log_dir,
            config_path=self.config_path,
            now=self.now,
            live_eligibility_matrix=self.matrix,
            global_gate=self.global_gate,
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
