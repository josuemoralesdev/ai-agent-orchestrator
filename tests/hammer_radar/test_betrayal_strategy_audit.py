from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from subprocess import run
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator import archive
from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.betrayal_strategy_audit import (
    BETRAYAL_PRIMARY_CANDIDATE,
    BETRAYAL_REJECTED,
    BETRAYAL_WATCHLIST,
    build_betrayal_strategy_audit,
    build_betrayal_strategy_row,
    invert_direction,
)
from src.app.hammer_radar.operator.models import OutcomeRecord, SignalRecord
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR


class BetrayalStrategyAuditTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict("os.environ", {LOG_DIR_ENV_VAR: str(self.log_dir)})
        self.env_patch.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_222m_like_row_becomes_primary_candidate(self) -> None:
        row = build_betrayal_strategy_row(self._row(timeframe="222m", sample_count=48, wins=6, total_pnl=-14.1309))

        self.assertEqual(BETRAYAL_PRIMARY_CANDIDATE, row["recommendation"])
        self.assertEqual(12.5, row["original"]["win_rate_pct"])
        self.assertEqual(87.5, row["betrayal"]["win_rate_pct"])
        self.assertEqual(14.1309, row["betrayal"]["total_pnl_pct"])
        self.assertEqual("short", row["betrayal_direction"])
        self.assertFalse(row["order_placed"])
        self.assertFalse(row["network_allowed"])

    def test_88m_like_row_becomes_watchlist_candidate(self) -> None:
        row = build_betrayal_strategy_row(self._row(timeframe="88m", sample_count=90, wins=33, total_pnl=-1.5995))

        self.assertEqual(BETRAYAL_WATCHLIST, row["recommendation"])
        self.assertEqual(36.67, row["original"]["win_rate_pct"])
        self.assertEqual(63.33, row["betrayal"]["win_rate_pct"])
        self.assertEqual(1.5995, row["betrayal"]["total_pnl_pct"])
        self.assertEqual("short", row["betrayal_direction"])

    def test_positive_original_total_pnl_is_rejected(self) -> None:
        row = build_betrayal_strategy_row(self._row(timeframe="13m", sample_count=48, wins=6, total_pnl=14.1309))

        self.assertEqual(BETRAYAL_REJECTED, row["recommendation"])
        self.assertIn("original total pnl is not negative", row["blockers"])
        self.assertLess(row["betrayal"]["total_pnl_pct"], 0)

    def test_low_sample_does_not_become_candidate(self) -> None:
        row = build_betrayal_strategy_row(self._row(timeframe="222m", sample_count=12, wins=1, total_pnl=-5.0))

        self.assertEqual(BETRAYAL_REJECTED, row["recommendation"])
        self.assertEqual("LOW_SAMPLE", row["confidence"])
        self.assertIn("sample_count below minimum 30", row["blockers"])

    def test_inverse_metrics_and_direction_are_computed(self) -> None:
        row = build_betrayal_strategy_row(self._row(timeframe="55m", direction="short", sample_count=40, wins=10, total_pnl=-8.0))

        self.assertEqual("long", row["betrayal_direction"])
        self.assertEqual(75.0, row["betrayal"]["win_rate_pct"])
        self.assertEqual(0.2, row["betrayal"]["avg_pnl_pct"])
        self.assertEqual(8.0, row["betrayal"]["total_pnl_pct"])
        self.assertEqual("short", invert_direction("long"))
        self.assertEqual("long", invert_direction("short"))

    def test_audit_payload_classifies_seeded_performance_rows(self) -> None:
        self._seed_group("primary-222m", "222m", "long", "ladder_close_50_618", wins=6, losses=42, total_pnl=-14.1309)
        self._seed_group("watch-88m", "88m", "long", "ladder_close_50_618", wins=33, losses=57, total_pnl=-1.5995)
        self._seed_group("normal-13m", "13m", "long", "ladder_close_50_618", wins=35, losses=13, total_pnl=8.0)

        payload = build_betrayal_strategy_audit(log_dir=self.log_dir)

        aggregate_primary = self._find(payload["timeframe_aggregate_primary_candidates"], timeframe="222m")
        aggregate_watchlist = self._find(payload["timeframe_aggregate_watchlist_candidates"], timeframe="88m")
        aggregate_rejected_normal = self._find(payload["timeframe_aggregate_rejected_candidates"], timeframe="13m")
        direction_primary = self._find(payload["direction_entry_mode_primary_candidates"], timeframe="222m")
        direction_watchlist = self._find(payload["direction_entry_mode_watchlist_candidates"], timeframe="88m")
        direction_rejected_normal = self._find(payload["direction_entry_mode_rejected_candidates"], timeframe="13m")
        legacy_primary = self._find(payload["primary_candidates"], timeframe="222m")
        legacy_watchlist = self._find(payload["watchlist_candidates"], timeframe="88m")
        self.assertEqual(BETRAYAL_PRIMARY_CANDIDATE, aggregate_primary["recommendation"])
        self.assertEqual("timeframe_aggregate", aggregate_primary["audit_scope"])
        self.assertIsNone(aggregate_primary["original_direction"])
        self.assertIsNone(aggregate_primary["entry_mode"])
        self.assertEqual(BETRAYAL_WATCHLIST, aggregate_watchlist["recommendation"])
        self.assertEqual("timeframe_aggregate", aggregate_watchlist["audit_scope"])
        self.assertEqual(BETRAYAL_REJECTED, aggregate_rejected_normal["recommendation"])
        self.assertEqual(BETRAYAL_PRIMARY_CANDIDATE, direction_primary["recommendation"])
        self.assertEqual("direction_entry_mode", direction_primary["audit_scope"])
        self.assertEqual(BETRAYAL_WATCHLIST, direction_watchlist["recommendation"])
        self.assertEqual("direction_entry_mode", direction_watchlist["audit_scope"])
        self.assertEqual(BETRAYAL_REJECTED, direction_rejected_normal["recommendation"])
        self.assertEqual(direction_primary, legacy_primary)
        self.assertEqual(direction_watchlist, legacy_watchlist)
        for key in (
            "timeframe_aggregate_leaderboard",
            "timeframe_aggregate_primary_candidates",
            "timeframe_aggregate_watchlist_candidates",
            "timeframe_aggregate_rejected_candidates",
            "direction_entry_mode_leaderboard",
            "direction_entry_mode_primary_candidates",
            "direction_entry_mode_watchlist_candidates",
            "direction_entry_mode_rejected_candidates",
        ):
            self.assertIn(key, payload)
        self.assertFalse(payload["live_execution_enabled"])
        self.assertFalse(payload["allow_live_orders"])
        self.assertTrue(payload["global_kill_switch"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["execution_attempted"])
        self.assertFalse(payload["order_payload_created"])
        self.assertFalse(payload["network_allowed"])
        self.assertFalse(payload["secrets_shown"])

    def test_api_endpoint_returns_safe_fields(self) -> None:
        self._seed_group("primary-222m", "222m", "long", "ladder_close_50_618", wins=6, losses=42, total_pnl=-14.1309)

        response = self.client.get("/strategy-performance/betrayal-audit")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("OK", payload["status"])
        self.assertEqual("R80", payload["phase"])
        aggregate_primary = self._find(payload["timeframe_aggregate_primary_candidates"], timeframe="222m")
        self.assertEqual(BETRAYAL_PRIMARY_CANDIDATE, aggregate_primary["recommendation"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["execution_attempted"])
        self.assertFalse(payload["order_payload_created"])
        self.assertFalse(payload["network_allowed"])
        self.assertFalse(payload["secrets_shown"])

    def test_cli_report_includes_primary_and_watchlist(self) -> None:
        self._seed_group("primary-222m", "222m", "long", "ladder_close_50_618", wins=6, losses=42, total_pnl=-14.1309)
        self._seed_group("watch-88m", "88m", "long", "ladder_close_50_618", wins=33, losses=57, total_pnl=-1.5995)

        result = run(
            [
                ".venv/bin/python",
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                str(self.log_dir),
                "betrayal-strategy-audit",
            ],
            cwd=Path(__file__).resolve().parents[2],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(0, result.returncode, msg=result.stderr)
        self.assertIn("TIMEFRAME AGGREGATE BETRAYAL", result.stdout)
        self.assertIn("DIRECTION / ENTRY-MODE BETRAYAL", result.stdout)
        self.assertIn("BETRAYAL_PRIMARY_CANDIDATE", result.stdout)
        self.assertIn("BETRAYAL_WATCHLIST", result.stdout)
        self.assertIn("222m aggregate", result.stdout)
        self.assertIn("88m aggregate", result.stdout)
        self.assertIn("222m long->short ladder_close_50_618", result.stdout)
        self.assertIn("88m long->short ladder_close_50_618", result.stdout)
        self.assertIn("No order placed", result.stdout)

    def test_existing_strategy_performance_and_betrayal_shadow_endpoints_still_pass(self) -> None:
        self._seed_group("normal-13m", "13m", "long", "ladder_close_50_618", wins=35, losses=13, total_pnl=8.0)

        for path in (
            "/strategy-performance/summary",
            "/strategy-performance/timeframes",
            "/strategy-performance/entry-modes",
            "/strategy-performance/live-eligibility",
            "/betrayal-shadow/outcomes",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(200, response.status_code)
                payload = response.json()
                self.assertFalse(payload["live_execution_enabled"])
                self.assertFalse(payload["order_placed"])

    @staticmethod
    def _row(*, timeframe: str, sample_count: int, wins: int, total_pnl: float, direction: str = "long") -> dict:
        losses = sample_count - wins
        return {
            "timeframe": timeframe,
            "direction": direction,
            "entry_mode": "ladder_close_50_618",
            "sample_count": sample_count,
            "wins": wins,
            "losses": losses,
            "win_rate_pct": round((wins / sample_count) * 100.0, 2),
            "avg_pnl_pct": round(total_pnl / sample_count, 4),
            "total_pnl_pct": round(total_pnl, 4),
            "best_pnl_pct": 0.5,
            "worst_pnl_pct": -0.5,
            "max_losing_streak": losses,
            "recommendation": "BLOCKED_FROM_LIVE",
        }

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
        *,
        wins: int,
        losses: int,
        total_pnl: float,
    ) -> None:
        sample_count = wins + losses
        win_pnl = 0.1
        loss_pnl = (total_pnl - wins * win_pnl) / losses if losses else 0.0
        pnl_values = [win_pnl] * wins + [loss_pnl] * losses
        base_time = datetime.now(UTC) - timedelta(hours=4)
        for index, pnl_pct in enumerate(pnl_values):
            timestamp = (base_time + timedelta(minutes=index)).isoformat()
            signal_id = f"BTCUSDT|{timeframe}|{direction}|{prefix}-{index}"
            signal = SignalRecord(
                signal_id=signal_id,
                symbol="BTCUSDT",
                timeframe=timeframe,
                direction=direction,
                timestamp=timestamp,
                hammer_strength=90.0,
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
        self.assertEqual(sample_count, len(pnl_values))


if __name__ == "__main__":
    unittest.main()
