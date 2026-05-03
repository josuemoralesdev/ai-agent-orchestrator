from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator import archive
from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.models import OutcomeRecord, SignalRecord
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR
from src.app.hammer_radar.operator.strategy_performance import (
    BLOCKED_FROM_LIVE,
    ELIGIBLE_FOR_FUTURE_TINY_LIVE,
    INSUFFICIENT_DATA,
    PAPER_ONLY,
    StrategyAuditConfig,
    build_live_eligibility_matrix,
    build_strategy_entry_mode_summary,
    build_strategy_performance_summary,
    build_strategy_timeframe_summary,
)


class StrategyPerformanceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict("os.environ", {LOG_DIR_ENV_VAR: str(self.log_dir)})
        self.env_patch.start()
        self.client = TestClient(app)
        self.config = StrategyAuditConfig(
            min_sample=3,
            min_win_rate=45.0,
            allowed_tiny_live_timeframes=("13m", "44m"),
            paper_only_timeframes=("4m", "8m", "88m"),
            context_only_timeframes=("4H", "13H", "13D", "888m"),
            blocked_timeframes=("22m", "55m", "222m", "444m"),
        )

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_audit_reads_ndjson_outcomes_and_signals_from_temp_log_dir(self) -> None:
        self._seed_group("read", "13m", "long", "ladder_close_50_618", (1.0, -0.5, 2.0))

        payload = build_strategy_performance_summary(log_dir=self.log_dir, config=self.config)

        self.assertEqual(3, payload["source_counts"]["signals"])
        self.assertEqual(3, payload["source_counts"]["outcomes"])
        self.assertEqual(3, payload["overall"]["sample_count"])
        self.assertFalse(payload["live_execution_enabled"])
        self.assertFalse(payload["order_placed"])

    def test_timeframe_summary_metrics_are_computed_correctly(self) -> None:
        self._seed_group("tf", "13m", "long", "ladder_close_50_618", (1.0, -0.5, 2.0))

        row = self._find(
            build_strategy_timeframe_summary(log_dir=self.log_dir, config=self.config)["timeframes"],
            timeframe="13m",
        )

        self.assertEqual(3, row["sample_count"])
        self.assertEqual(2, row["wins"])
        self.assertEqual(1, row["losses"])
        self.assertEqual(66.67, row["win_rate_pct"])
        self.assertEqual(0.8333, row["avg_pnl_pct"])
        self.assertEqual(2.5, row["total_pnl_pct"])
        self.assertEqual(2.0, row["best_pnl_pct"])
        self.assertEqual(-0.5, row["worst_pnl_pct"])
        self.assertEqual(1, row["max_losing_streak"])

    def test_direction_summary_metrics_are_computed_correctly(self) -> None:
        self._seed_group("long", "13m", "long", "ladder_close_50_618", (1.0, -0.5, 2.0))
        self._seed_group("short", "13m", "short", "ladder_close_50_618", (-1.0, -0.25, 0.5))

        row = self._find(
            build_strategy_performance_summary(log_dir=self.log_dir, config=self.config)["groups"]["direction"],
            direction="short",
        )

        self.assertEqual(3, row["sample_count"])
        self.assertEqual(1, row["wins"])
        self.assertEqual(2, row["losses"])
        self.assertEqual(-0.25, row["avg_pnl_pct"])

    def test_entry_mode_summary_metrics_are_computed_correctly(self) -> None:
        self._seed_group("ladder", "13m", "long", "ladder_close_50_618", (1.0, -0.5, 2.0))
        self._seed_group("fib", "13m", "long", "fib_618", (-1.0, -0.25, 0.5))

        row = self._find(
            build_strategy_entry_mode_summary(log_dir=self.log_dir, config=self.config)["entry_modes"],
            entry_mode="ladder_close_50_618",
        )

        self.assertEqual(3, row["sample_count"])
        self.assertEqual(2, row["wins"])
        self.assertEqual(0.8333, row["avg_pnl_pct"])

    def test_ladder_close_50_618_can_be_recommended_when_thresholds_pass(self) -> None:
        self._seed_group("eligible", "13m", "long", "ladder_close_50_618", (1.0, -0.5, 2.0))

        row = self._find(
            build_live_eligibility_matrix(log_dir=self.log_dir, config=self.config)["recommendations"],
            timeframe="13m",
            direction="long",
            entry_mode="ladder_close_50_618",
        )

        self.assertEqual(ELIGIBLE_FOR_FUTURE_TINY_LIVE, row["recommendation"])
        self.assertFalse(row["live_execution_enabled"])
        self.assertFalse(row["order_placed"])
        self.assertTrue(row["no_order_payload_created"])

    def test_negative_timeframe_is_blocked_from_live(self) -> None:
        self._seed_group("weak", "55m", "long", "ladder_close_50_618", (-1.0, -0.5, -0.25))

        row = self._find(
            build_live_eligibility_matrix(log_dir=self.log_dir, config=self.config)["recommendations"],
            timeframe="55m",
        )

        self.assertEqual(BLOCKED_FROM_LIVE, row["recommendation"])

    def test_4m_and_8m_remain_paper_only_despite_positive_metrics(self) -> None:
        self._seed_group("four", "4m", "long", "ladder_close_50_618", (1.0, -0.5, 2.0))
        self._seed_group("eight", "8m", "long", "ladder_close_50_618", (1.0, -0.5, 2.0))

        rows = build_live_eligibility_matrix(log_dir=self.log_dir, config=self.config)["recommendations"]

        self.assertEqual(PAPER_ONLY, self._find(rows, timeframe="4m")["recommendation"])
        self.assertEqual(PAPER_ONLY, self._find(rows, timeframe="8m")["recommendation"])

    def test_short_groups_do_not_become_live_eligible(self) -> None:
        self._seed_group("short", "13m", "short", "ladder_close_50_618", (1.0, -0.5, 2.0))

        row = self._find(
            build_live_eligibility_matrix(log_dir=self.log_dir, config=self.config)["recommendations"],
            direction="short",
        )

        self.assertEqual(PAPER_ONLY, row["recommendation"])
        self.assertIn("shorts remain paper/operator visibility only", row["blockers"])

    def test_low_sample_groups_become_insufficient_data(self) -> None:
        self._seed_group("small", "44m", "long", "ladder_close_50_618", (1.0, 2.0))

        row = self._find(
            build_live_eligibility_matrix(log_dir=self.log_dir, config=self.config)["recommendations"],
            timeframe="44m",
        )

        self.assertEqual(INSUFFICIENT_DATA, row["recommendation"])
        self.assertEqual("LOW_SAMPLE", row["confidence"])

    def test_api_endpoints_return_safety_flags_and_no_secrets(self) -> None:
        for path in (
            "/strategy-performance/summary",
            "/strategy-performance/timeframes",
            "/strategy-performance/entry-modes",
            "/strategy-performance/live-eligibility",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(200, response.status_code)
                payload = response.json()
                self.assertFalse(payload["live_execution_enabled"])
                self.assertFalse(payload["order_placed"])
                self.assertFalse(payload["execution_enabled"])
                self.assertTrue(payload["no_order_payload_created"])
                self.assertFalse(payload["secrets_shown"])

    @staticmethod
    def _find(rows: list[dict], **filters: str) -> dict:
        for row in rows:
            if all(row.get(key) == value for key, value in filters.items()):
                return row
        raise AssertionError(f"row not found: {filters}")

    def _seed_group(
        self,
        prefix: str,
        timeframe: str,
        direction: str,
        entry_mode: str,
        pnl_values: tuple[float, ...],
    ) -> None:
        base_time = datetime.now(UTC) - timedelta(hours=1)
        for index, pnl_pct in enumerate(pnl_values):
            timestamp = (base_time + timedelta(minutes=index)).isoformat()
            signal_id = f"BTCUSDT|{timeframe}|{direction}|{prefix}-{index}"
            signal = SignalRecord(
                signal_id=signal_id,
                symbol="BTCUSDT",
                timeframe=timeframe,
                direction=direction,
                timestamp=timestamp,
                hammer_strength=100.0,
                hammer_high=101.0,
                hammer_low=94.0,
                fib_50=100.5,
                fib_618=100.0,
                fib_650=99.5,
                fib_786=98.5,
                invalidation=95.0,
                bias_timeframe="4H",
                bias_direction="bullish" if direction == "long" else "bearish",
                bias_aligned=True,
                same_direction_streak=0,
                opposite_direction_streak=0,
                tradable=True,
                trend_direction="bullish" if direction == "long" else "bearish",
                trend_strength_score=0.6,
            )
            outcome = OutcomeRecord(
                signal_id=signal_id,
                symbol="BTCUSDT",
                timeframe=timeframe,
                direction=direction,
                timestamp=timestamp,
                entry_price=100.0,
                exit_price=100.0 + pnl_pct,
                fill_status="filled",
                outcome="win" if pnl_pct > 0 else "loss",
                mae_pct=abs(pnl_pct) / 2.0,
                mfe_pct=abs(pnl_pct),
                pnl_pct=pnl_pct,
                stop_hit=pnl_pct <= 0,
                evaluated_at=(base_time + timedelta(minutes=index + 1)).isoformat(),
                entry_mode=entry_mode,
            )
            archive.append_signal(signal, log_dir=self.log_dir)
            archive.append_outcome(outcome, log_dir=self.log_dir)


if __name__ == "__main__":
    unittest.main()
