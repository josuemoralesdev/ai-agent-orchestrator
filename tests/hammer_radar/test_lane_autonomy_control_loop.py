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
    ARMED_DRY_RUN_INTENT,
    BLOCKED,
    CONFIRM_AUTONOMY_DECISION_RECORDING_PHRASE,
    IGNORE,
    LANE_AUTONOMY_DECISIONS_LEDGER,
    LANE_AUTONOMY_PREVIEW,
    LANE_AUTONOMY_RECORDED,
    LANE_AUTONOMY_REJECTED,
    PAPER_ENTRY_INTENT,
    PAPER_OBSERVE,
    TINY_LIVE_GATE_REVIEW,
    build_lane_autonomy_control_loop_status,
    build_non_executing_strategy_intent,
    load_lane_autonomy_decisions,
)
from src.app.hammer_radar.operator.strategy_performance import ELIGIBLE_FOR_FUTURE_TINY_LIVE

LANE_13M = "BTCUSDT|13m|long|ladder_close_50_618"
LANE_44M = "BTCUSDT|44m|long|ladder_close_50_618"
LANE_8M = "BTCUSDT|8m|long|ladder_close_50_618"


class LaneAutonomyControlLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.log_dir = self.root / "logs"
        self.config_path = self.root / "lane_controls.json"
        self.now = datetime(2026, 5, 25, 16, 0, tzinfo=UTC)
        self._write_config(
            [
                self._lane("13m", "armed_dry_run", max_daily_trades=2),
                self._lane("44m", "paper", max_daily_trades=2),
                self._lane("8m", "tiny_live", max_daily_trades=2),
            ]
        )
        self.matrix = {
            "recommendations": [
                self._eligibility("13m", ELIGIBLE_FOR_FUTURE_TINY_LIVE),
                self._eligibility("8m", ELIGIBLE_FOR_FUTURE_TINY_LIVE),
            ]
        }
        self.global_gate_ready = {"status": "FIRST_LIVE_ACTIVATION_READY", "execution_enabled_by_gate": True}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_preview_mode_writes_no_decision_records(self) -> None:
        payload = self._status(candidates=[self._candidate("44m", seconds_old=60)])

        self.assertEqual(LANE_AUTONOMY_PREVIEW, payload["status"])
        self.assertEqual(1, payload["decisions_count"])
        self.assertEqual(0, payload["recorded_count"])
        self.assertFalse((self.log_dir / LANE_AUTONOMY_DECISIONS_LEDGER).exists())

    def test_wrong_confirmation_rejects_recording(self) -> None:
        payload = self._status(
            record_decision=True,
            confirm_decision_record="wrong",
            candidates=[self._candidate("44m", seconds_old=60)],
        )

        self.assertEqual(LANE_AUTONOMY_REJECTED, payload["status"])
        self.assertEqual("missing or invalid decision-record confirmation", payload["rejection_reason"])
        self.assertEqual(0, payload["recorded_count"])
        self.assertFalse((self.log_dir / LANE_AUTONOMY_DECISIONS_LEDGER).exists())

    def test_exact_confirmation_records_decision_records_only(self) -> None:
        payload = self._status(
            record_decision=True,
            confirm_decision_record=CONFIRM_AUTONOMY_DECISION_RECORDING_PHRASE,
            candidates=[self._candidate("44m", seconds_old=60)],
        )
        records = load_lane_autonomy_decisions(log_dir=self.log_dir)

        self.assertEqual(LANE_AUTONOMY_RECORDED, payload["status"])
        self.assertEqual(1, payload["recorded_count"])
        self.assertEqual(1, len(records))
        self.assertEqual("LANE_AUTONOMY_DECISION", records[0]["event_type"])
        self.assertEqual(PAPER_ENTRY_INTENT, records[0]["autonomy_decision"])
        self.assertFalse(records[0]["safety"]["order_placed"])
        self.assertFalse(records[0]["safety"]["real_order_placed"])
        self.assertFalse(records[0]["safety"]["execution_attempted"])
        self.assertFalse(records[0]["safety"]["order_payload_created"])
        self.assertFalse(records[0]["safety"]["network_allowed"])
        self.assertFalse(records[0]["safety"]["secrets_shown"])

    def test_paper_lane_produces_paper_entry_intent_for_fresh_route(self) -> None:
        payload = self._status(candidates=[self._candidate("44m", seconds_old=60)])

        self.assertIn(payload["decisions"][0]["autonomy_decision"], {PAPER_ENTRY_INTENT, PAPER_OBSERVE})
        self.assertEqual(PAPER_ENTRY_INTENT, payload["decisions"][0]["autonomy_decision"])

    def test_armed_dry_run_lane_produces_armed_dry_run_intent(self) -> None:
        payload = self._status(candidates=[self._candidate("13m", seconds_old=30)])

        self.assertEqual(ARMED_DRY_RUN_INTENT, payload["decisions"][0]["autonomy_decision"])

    def test_tiny_live_lane_produces_gate_review_not_order(self) -> None:
        payload = self._status(
            candidates=[self._candidate("8m", seconds_old=30)],
            global_gate=self.global_gate_ready,
        )

        self.assertEqual(TINY_LIVE_GATE_REVIEW, payload["decisions"][0]["autonomy_decision"])
        self.assertFalse(payload["safety"]["order_placed"])
        self.assertFalse(payload["safety"]["execution_attempted"])

    def test_stale_or_no_candidate_produces_blocked_or_ignore(self) -> None:
        stale = self._status(candidates=[self._candidate("13m", seconds_old=121)])
        empty = self._status(candidates=[])

        self.assertIn(stale["decisions"][0]["autonomy_decision"], {BLOCKED, IGNORE})
        self.assertEqual(IGNORE, empty["decisions"][0]["autonomy_decision"])

    def test_strategy_intent_contains_no_direct_executable_order_payload(self) -> None:
        intent = build_non_executing_strategy_intent(self._candidate("44m", seconds_old=60), lane=self._lane("44m", "paper"))
        rendered = json.dumps(intent).lower()

        self.assertNotIn("/fapi/v1/order", rendered)
        self.assertNotIn("signature", rendered)
        self.assertIsNone(intent["exit_policy"]["direct_exchange_payload"])
        self.assertIsNone(intent["size_policy"]["direct_live_quantity"])

    def test_safety_flags_are_false_and_separation_true(self) -> None:
        payload = self._status(candidates=[self._candidate("44m", seconds_old=60)])

        self.assertEqual(self._safe(), payload["safety"])

    def test_ledger_writes_append_only_decision_records(self) -> None:
        first = self._status(
            record_decision=True,
            confirm_decision_record=CONFIRM_AUTONOMY_DECISION_RECORDING_PHRASE,
            candidates=[self._candidate("44m", seconds_old=60, candidate_id="first")],
        )
        second = self._status(
            record_decision=True,
            confirm_decision_record=CONFIRM_AUTONOMY_DECISION_RECORDING_PHRASE,
            candidates=[self._candidate("44m", seconds_old=60, candidate_id="second")],
        )
        records = load_lane_autonomy_decisions(log_dir=self.log_dir)

        self.assertEqual(LANE_AUTONOMY_RECORDED, first["status"])
        self.assertEqual(LANE_AUTONOMY_RECORDED, second["status"])
        self.assertEqual(["first", "second"], [record["candidate_id"] for record in records])

    def test_cli_mode_exists_and_returns_compact_status(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                str(self.log_dir),
                "lane-autonomy-control-loop",
            ],
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": "."},
        )

        payload = json.loads(result.stdout)
        self.assertIn("decisions", payload)
        self.assertIn(payload["status"], {LANE_AUTONOMY_PREVIEW, LANE_AUTONOMY_REJECTED})
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
            payload = self._status(candidates=[self._candidate("44m", seconds_old=60)])

        execute_live_order.assert_not_called()
        preview_payload.assert_not_called()
        protective_preview.assert_not_called()
        submit_test_order.assert_not_called()
        rendered = json.dumps(payload).lower()
        self.assertNotIn("binance_futures_connector", rendered)
        self.assertFalse(payload["safety"]["order_payload_created"])
        self.assertFalse(payload["safety"]["network_allowed"])
        self.assertFalse(payload["safety"]["execution_attempted"])

    def _status(self, **kwargs: object) -> dict[str, object]:
        return build_lane_autonomy_control_loop_status(
            log_dir=self.log_dir,
            config_path=self.config_path,
            now=self.now,
            live_eligibility_matrix=self.matrix,
            global_gate=kwargs.pop("global_gate", {"status": "FIRST_LIVE_BLOCKED", "execution_enabled_by_gate": False}),
            **kwargs,
        )

    def _candidate(
        self,
        timeframe: str,
        *,
        symbol: str = "BTCUSDT",
        seconds_old: int,
        candidate_id: str | None = None,
    ) -> dict[str, object]:
        return {
            "candidate_id": candidate_id or f"{symbol}-{timeframe}-{seconds_old}",
            "symbol": symbol,
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

    def _lane(self, timeframe: str, mode: str, *, max_daily_trades: int = 1) -> dict[str, object]:
        freshness = {"13m": 120, "44m": 300, "8m": 60}.get(timeframe, 60)
        return {
            "symbol": "BTCUSDT",
            "timeframe": timeframe,
            "direction": "long",
            "entry_mode": "ladder_close_50_618",
            "mode": mode,
            "max_daily_trades": max_daily_trades,
            "max_daily_loss_pct": 0.25,
            "freshness_seconds": freshness,
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
