from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from src.app.hammer_radar.operator.autonomous_paper_lane_execution import (
    ARMED_DRY_RUN_ENTRY_RECORDED,
    AUTONOMOUS_PAPER_LANE_EXECUTIONS_LEDGER,
    CONFIRM_PAPER_ONLY_PHRASE,
    PAPER_BLOCKED,
    PAPER_ENTRY_RECORDED,
    PAPER_LANE_PREVIEW,
    PAPER_LANE_RECORDED,
    PAPER_LANE_REJECTED,
    PAPER_SHADOW_FOR_TINY_LIVE,
    append_paper_lane_execution,
    build_autonomous_paper_lane_execution_status,
    build_paper_execution_from_routed_candidate,
    compute_lane_cooldown_status,
    compute_lane_daily_count,
    load_paper_lane_executions,
)
from src.app.hammer_radar.operator.strategy_performance import ELIGIBLE_FOR_FUTURE_TINY_LIVE


LANE_13M = "BTCUSDT|13m|long|ladder_close_50_618"
LANE_44M = "BTCUSDT|44m|long|ladder_close_50_618"


class AutonomousPaperLaneExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.log_dir = self.root / "logs"
        self.config_path = self.root / "lane_controls.json"
        self.now = datetime(2026, 5, 24, 15, 0, tzinfo=UTC)
        self._write_config(
            [
                self._lane("13m", "armed_dry_run", max_daily_trades=1, cooldown_after_loss_minutes=120),
                self._lane("44m", "paper", max_daily_trades=1, cooldown_after_loss_minutes=180),
                self._lane("8m", "tiny_live", max_daily_trades=1, cooldown_after_loss_minutes=120),
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

    def test_preview_mode_records_no_paper_executions(self) -> None:
        payload = self._status(candidates=[self._candidate("44m", seconds_old=60)])

        self.assertEqual(PAPER_LANE_PREVIEW, payload["status"])
        self.assertEqual(1, payload["paper_recordable_count"])
        self.assertEqual(0, payload["recorded_count"])
        self.assertFalse((self.log_dir / AUTONOMOUS_PAPER_LANE_EXECUTIONS_LEDGER).exists())

    def test_wrong_confirmation_rejects_execution(self) -> None:
        payload = self._status(
            execute_paper=True,
            confirm_paper_only="wrong",
            candidates=[self._candidate("44m", seconds_old=60)],
        )

        self.assertEqual(PAPER_LANE_REJECTED, payload["status"])
        self.assertEqual("missing or invalid paper-only confirmation", payload["rejection_reason"])
        self.assertEqual(0, payload["recorded_count"])
        self.assertFalse((self.log_dir / AUTONOMOUS_PAPER_LANE_EXECUTIONS_LEDGER).exists())

    def test_exact_confirmation_records_only_paper_records(self) -> None:
        payload = self._status(
            execute_paper=True,
            confirm_paper_only=CONFIRM_PAPER_ONLY_PHRASE,
            candidates=[self._candidate("44m", seconds_old=60)],
        )
        records = load_paper_lane_executions(log_dir=self.log_dir)

        self.assertEqual(PAPER_LANE_RECORDED, payload["status"])
        self.assertEqual(1, payload["recorded_count"])
        self.assertEqual(1, len(records))
        self.assertEqual(PAPER_ENTRY_RECORDED, records[0]["paper_action"])
        self.assertFalse(records[0]["safety"]["order_placed"])
        self.assertFalse(records[0]["safety"]["real_order_placed"])
        self.assertFalse(records[0]["safety"]["execution_attempted"])
        self.assertFalse(records[0]["safety"]["order_payload_created"])
        self.assertFalse(records[0]["safety"]["network_allowed"])
        self.assertFalse(records[0]["safety"]["secrets_shown"])
        self.assertTrue(records[0]["safety"]["paper_live_separation_intact"])

    def test_fresh_13m_armed_dry_run_candidate_creates_armed_dry_run_record(self) -> None:
        payload = self._status(candidates=[self._candidate("13m", seconds_old=30)])

        self.assertEqual(ARMED_DRY_RUN_ENTRY_RECORDED, payload["preview_records"][0]["paper_action"])
        self.assertEqual(0, payload["paper_blocked_count"])

    def test_fresh_44m_paper_candidate_creates_paper_record(self) -> None:
        payload = self._status(candidates=[self._candidate("44m", seconds_old=60)])

        self.assertEqual(PAPER_ENTRY_RECORDED, payload["preview_records"][0]["paper_action"])

    def test_stale_candidate_is_blocked(self) -> None:
        payload = self._status(candidates=[self._candidate("13m", seconds_old=121)])

        self.assertEqual(PAPER_BLOCKED, payload["preview_records"][0]["paper_action"])
        self.assertIn("candidate route_status is not ROUTED_TO_LANE", payload["preview_records"][0]["blockers"])

    def test_unknown_lane_blocked(self) -> None:
        payload = self._status(candidates=[self._candidate("13m", symbol="ETHUSDT", seconds_old=30)])

        self.assertEqual(PAPER_BLOCKED, payload["preview_records"][0]["paper_action"])
        self.assertIn("no matching lane", payload["preview_records"][0]["blockers"])

    def test_max_daily_trades_blocks_additional_records(self) -> None:
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
        payload = self._status(candidates=[self._candidate("44m", seconds_old=60)])

        self.assertEqual(1, compute_lane_daily_count(LANE_44M, log_dir=self.log_dir, day=self.now.date()))
        self.assertEqual(PAPER_BLOCKED, payload["preview_records"][0]["paper_action"])
        self.assertIn("lane max_daily_trades exceeded", payload["preview_records"][0]["blockers"])

    def test_cooldown_blocks_records_when_active(self) -> None:
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
        cooldown = compute_lane_cooldown_status(
            LANE_44M,
            cooldown_after_loss_minutes=180,
            log_dir=self.log_dir,
            now=self.now,
        )
        payload = self._status(candidates=[self._candidate("44m", seconds_old=60)])

        self.assertTrue(cooldown["active"])
        self.assertEqual(PAPER_BLOCKED, payload["preview_records"][0]["paper_action"])
        self.assertIn("lane cooldown_after_loss_minutes is active", payload["preview_records"][0]["blockers"])

    def test_tiny_live_lane_creates_paper_shadow_only_not_real_order(self) -> None:
        payload = self._status(
            candidates=[self._candidate("8m", seconds_old=30)],
            global_gate=self.global_gate_ready,
        )

        self.assertEqual(PAPER_SHADOW_FOR_TINY_LIVE, payload["preview_records"][0]["paper_action"])
        self.assertFalse(payload["preview_records"][0]["safety"]["order_placed"])
        self.assertFalse(payload["preview_records"][0]["safety"]["real_order_placed"])
        self.assertFalse(payload["preview_records"][0]["safety"]["execution_attempted"])

    def test_safety_flags_are_always_false_and_separation_true(self) -> None:
        payload = self._status(candidates=[self._candidate("44m", seconds_old=60)])

        self.assertEqual(self._safe(), payload["safety"])
        self.assertEqual(self._safe(), payload["preview_records"][0]["safety"])

    def test_ledger_writes_append_only_paper_records(self) -> None:
        first = self._status(
            execute_paper=True,
            confirm_paper_only=CONFIRM_PAPER_ONLY_PHRASE,
            candidates=[self._candidate("44m", seconds_old=60, candidate_id="first")],
        )
        self._write_config([self._lane("44m", "paper", max_daily_trades=2, cooldown_after_loss_minutes=180)])
        second = self._status(
            execute_paper=True,
            confirm_paper_only=CONFIRM_PAPER_ONLY_PHRASE,
            candidates=[self._candidate("44m", seconds_old=60, candidate_id="second")],
        )
        records = load_paper_lane_executions(log_dir=self.log_dir)

        self.assertEqual(PAPER_LANE_RECORDED, first["status"])
        self.assertEqual(PAPER_LANE_RECORDED, second["status"])
        self.assertEqual(2, len(records))
        self.assertEqual(["first", "second"], [record["candidate_id"] for record in records])

    def test_cli_mode_exists_and_returns_compact_status(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                str(self.log_dir),
                "autonomous-paper-lane-execution",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        payload = json.loads(result.stdout)
        self.assertIn(payload["status"], {PAPER_LANE_PREVIEW, PAPER_LANE_REJECTED, "PAPER_LANE_PARTIAL"})
        self.assertIn("preview_records", payload)
        self.assertNotIn("recommendations", result.stdout)
        self.assertLess(len(result.stdout), 8000)

    def test_no_binance_order_payload_or_network_calls_occur(self) -> None:
        payload = self._status(candidates=[self._candidate("44m", seconds_old=60)])
        rendered = json.dumps(payload).lower()

        self.assertNotIn("binance_futures_connector", rendered)
        self.assertFalse(payload["safety"]["order_payload_created"])
        self.assertFalse(payload["safety"]["network_allowed"])
        self.assertFalse(payload["safety"]["execution_attempted"])

    def test_source_safety_true_blocks_record(self) -> None:
        record = build_paper_execution_from_routed_candidate(
            {
                "route_status": "ROUTED_TO_LANE",
                "candidate_id": "unsafe",
                "lane_key": LANE_44M,
                "symbol": "BTCUSDT",
                "timeframe": "44m",
                "direction": "long",
                "entry_mode": "ladder_close_50_618",
                "candidate_age_seconds": 60,
                "freshness_seconds": 300,
                "lane_mode": "paper",
                "route_action": "PAPER_OBSERVE",
                "safety": {"network_allowed": True},
            },
            lane=self._lane("44m", "paper"),
            existing_records=[],
            now=self.now,
        )

        self.assertEqual(PAPER_BLOCKED, record["paper_action"])
        self.assertFalse(record["safety"]["paper_live_separation_intact"])
        self.assertIn("source safety reported execution/order/network/secret activity", record["blockers"])

    def _status(self, **kwargs: object) -> dict[str, object]:
        return build_autonomous_paper_lane_execution_status(
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

    def _lane(
        self,
        timeframe: str,
        mode: str,
        *,
        max_daily_trades: int = 1,
        cooldown_after_loss_minutes: int = 120,
    ) -> dict[str, object]:
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
            "cooldown_after_loss_minutes": cooldown_after_loss_minutes,
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
