from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator import archive, inspect, positions
from src.app.hammer_radar.operator.models import OutcomeRecord, SignalRecord
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR


class InspectCliTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        log_dir = Path(self.temp_dir.name)

        self.original_archive_log_dir = archive.LOG_DIR
        self.original_signals_path = archive.SIGNALS_PATH
        self.original_outcomes_path = archive.OUTCOMES_PATH
        self.original_positions_log_dir = positions.LOG_DIR
        self.original_positions_path = positions.POSITIONS_PATH
        self.original_position_events_path = positions.POSITION_EVENTS_PATH

        archive.LOG_DIR = log_dir
        archive.SIGNALS_PATH = log_dir / "signals.ndjson"
        archive.OUTCOMES_PATH = log_dir / "outcomes.ndjson"
        positions.LOG_DIR = log_dir
        positions.POSITIONS_PATH = log_dir / "positions.ndjson"
        positions.POSITION_EVENTS_PATH = log_dir / "position_events.ndjson"

        signal = self._build_signal()
        archive.append_signal(signal)
        archive.append_outcome(
            OutcomeRecord(
                signal_id=signal.signal_id,
                symbol=signal.symbol,
                timeframe=signal.timeframe,
                direction=signal.direction,
                timestamp=signal.timestamp,
                entry_price=100.0,
                exit_price=95.0,
                fill_status="filled",
                outcome="loss",
                mae_pct=5.0,
                mfe_pct=1.0,
                pnl_pct=-5.0,
                stop_hit=True,
                evaluated_at="2026-04-24T16:42:59.999000+00:00",
            )
        )
        created = positions.create_paper_position(signal)
        assert created is not None
        positions.evaluate_open_positions(
            [created],
            {
                "13m": {
                    "high": 101.0,
                    "low": 94.0,
                    "open": 100.0,
                    "close": 95.0,
                    "timestamp": "2026-04-24T16:55:59.999000+00:00",
                }
            },
        )

    def tearDown(self) -> None:
        archive.LOG_DIR = self.original_archive_log_dir
        archive.SIGNALS_PATH = self.original_signals_path
        archive.OUTCOMES_PATH = self.original_outcomes_path
        positions.LOG_DIR = self.original_positions_log_dir
        positions.POSITIONS_PATH = self.original_positions_path
        positions.POSITION_EVENTS_PATH = self.original_position_events_path
        self.temp_dir.cleanup()

    def test_summary_includes_expected_totals(self) -> None:
        output = inspect.build_summary_text()

        self.assertIn("total_signals: 1", output)
        self.assertIn(f"archive_log_dir: {archive.LOG_DIR}", output)
        self.assertIn("tradable_signals: 1", output)
        self.assertIn("total_outcomes: 1", output)
        self.assertIn("total_paper_positions: 1", output)
        self.assertIn("open_paper_positions: 0", output)
        self.assertIn("closed_paper_positions: 1", output)
        self.assertIn("total_closed_pnl_usd: -5.0000", output)
        self.assertIn("total_closed_pnl_pct: -5.0000%", output)

    def test_positions_view_filters_closed_positions(self) -> None:
        output = inspect.build_positions_text(status="closed")

        self.assertIn("HAMMER RADAR POSITIONS [closed]", output)
        self.assertIn("status=closed", output)
        self.assertIn("pnl_usd=-5.00", output)
        self.assertIn("close_reason=stop", output)

    def test_signals_view_respects_limit(self) -> None:
        archive.append_signal(
            self._build_signal(
                signal_id="BTCUSDT|13m|short|2026-04-24T16:40:59.999000+00:00",
                direction="short",
                timestamp="2026-04-24T16:40:59.999000+00:00",
            )
        )

        output = inspect.build_signals_text(limit=1)

        self.assertIn("HAMMER RADAR SIGNALS", output)
        self.assertIn("BTCUSDT|13m|short|2026-04-24T16:40:59.999000+00:00", output)
        self.assertNotIn("BTCUSDT|13m|long|2026-04-24T16:27:59.999000+00:00", output)

    def test_default_log_dir_behavior_remains_unchanged(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(archive.get_log_dir(), archive.LOG_DIR)
            self.assertEqual(archive.get_signals_path(), archive.SIGNALS_PATH)

    def test_summary_reads_alternate_log_dir_without_creating_missing_files(self) -> None:
        alternate_dir = Path(self.temp_dir.name) / "alternate"
        missing_dir = Path(self.temp_dir.name) / "missing"
        signal = self._build_signal(signal_id="alt|1", timestamp="2026-04-24T17:27:59.999000+00:00")
        archive.append_signal(signal, log_dir=alternate_dir)
        archive.append_outcome(
            OutcomeRecord(
                signal_id=signal.signal_id,
                symbol=signal.symbol,
                timeframe=signal.timeframe,
                direction=signal.direction,
                timestamp=signal.timestamp,
                entry_price=100.0,
                exit_price=101.0,
                fill_status="filled",
                outcome="win",
                mae_pct=0.1,
                mfe_pct=1.0,
                pnl_pct=1.0,
                stop_hit=False,
                evaluated_at="2026-04-24T17:42:59.999000+00:00",
            ),
            log_dir=alternate_dir,
        )

        output = inspect.build_summary_text(log_dir=alternate_dir)
        missing_output = inspect.build_summary_text(log_dir=missing_dir)

        self.assertIn(f"archive_log_dir: {alternate_dir}", output)
        self.assertIn("total_signals: 1", output)
        self.assertIn("total_outcomes: 1", output)
        self.assertIn("total_signals: 0", missing_output)
        self.assertFalse(missing_dir.exists())

    def test_env_log_dir_override_reads_alternate_fixture(self) -> None:
        alternate_dir = Path(self.temp_dir.name) / "env-alternate"
        archive.append_signal(self._build_signal(signal_id="env|1"), log_dir=alternate_dir)

        with patch.dict("os.environ", {LOG_DIR_ENV_VAR: str(alternate_dir)}):
            output = inspect.build_summary_text()

        self.assertIn(f"archive_log_dir: {alternate_dir}", output)
        self.assertIn("total_signals: 1", output)

    def test_runtime_archive_path_resolves_from_env_without_mutating_other_archive(self) -> None:
        runtime_dir = Path(self.temp_dir.name) / "runtime-output"
        old_archive_dir = Path(self.temp_dir.name) / "old-archive"
        archive.append_signal(self._build_signal(signal_id="old|1"), log_dir=old_archive_dir)

        with patch.dict("os.environ", {LOG_DIR_ENV_VAR: str(runtime_dir)}):
            resolved = archive.get_log_dir(use_env=True)
            output = inspect.build_summary_text()

        self.assertEqual(runtime_dir, resolved)
        self.assertIn(f"archive_log_dir: {runtime_dir}", output)
        self.assertIn("total_signals: 0", output)
        self.assertFalse(runtime_dir.exists())
        self.assertTrue((old_archive_dir / "signals.ndjson").exists())

    def test_r9_coverage_empty_archive(self) -> None:
        empty_dir = Path(self.temp_dir.name) / "empty-r9"

        output = inspect.build_r9_coverage_text(log_dir=empty_dir)

        self.assertIn(f"archive_log_dir: {empty_dir}", output)
        self.assertIn("total_signals: 0", output)
        self.assertIn("signals_missing_r9_metadata: 0", output)
        self.assertIn("r9_metadata_coverage_pct: 0.00%", output)
        self.assertFalse(empty_dir.exists())

    def test_r9_coverage_pre_r9_records_report_missing_metadata(self) -> None:
        pre_r9_dir = Path(self.temp_dir.name) / "pre-r9"
        archive.append_signal(self._build_signal(signal_id="pre-r9|1"), log_dir=pre_r9_dir)

        output = inspect.build_r9_coverage_text(log_dir=pre_r9_dir)

        self.assertIn("total_signals: 1", output)
        self.assertIn("signals_with_rsi: 0", output)
        self.assertIn("signals_with_divergence: 0", output)
        self.assertIn("signals_with_trigger_fields: 0", output)
        self.assertIn("signals_missing_r9_metadata: 1", output)
        self.assertIn("r9_metadata_coverage_pct: 0.00%", output)

    def test_r9_coverage_r9_aware_records_report_coverage(self) -> None:
        r9_dir = Path(self.temp_dir.name) / "r9-aware"
        archive.append_signal(
            self._build_signal(
                signal_id="r9-aware|1",
                rsi_value=21.5,
                rsi_state="oversold",
                divergence_type="bullish",
                divergence_confirmed=True,
                extreme_trigger=True,
                critical_trigger=True,
                micro_scalp_candidate=True,
                requires_human_approval=True,
            ),
            log_dir=r9_dir,
        )

        output = inspect.build_r9_coverage_text(log_dir=r9_dir)

        self.assertIn("total_signals: 1", output)
        self.assertIn("signals_with_rsi: 1", output)
        self.assertIn("signals_with_divergence: 1", output)
        self.assertIn("signals_with_trigger_fields: 1", output)
        self.assertIn("signals_missing_r9_metadata: 0", output)
        self.assertIn("r9_metadata_coverage_pct: 100.00%", output)

    def test_signals_view_includes_r9_metadata_when_present(self) -> None:
        archive.append_signal(
            self._build_signal(
                signal_id="BTCUSDT|13m|long|2026-04-24T17:27:59.999000+00:00",
                timestamp="2026-04-24T17:27:59.999000+00:00",
                rsi_value=24.75,
                rsi_state="oversold",
                divergence_type="bullish",
                divergence_confirmed=True,
                extreme_trigger=True,
                critical_trigger=True,
                micro_scalp_candidate=True,
                requires_human_approval=True,
            )
        )

        output = inspect.build_signals_text(limit=1)

        self.assertIn("rsi=24.75", output)
        self.assertIn("rsi_state=oversold", output)
        self.assertIn("div=bullish", output)
        self.assertIn("div_confirmed=Y", output)
        self.assertIn("extreme=Y", output)
        self.assertIn("critical=Y", output)
        self.assertIn("micro_scalp=Y", output)
        self.assertIn("human_approval=Y", output)

    def test_daily_report_works_on_empty_archive(self) -> None:
        empty_dir = Path(self.temp_dir.name) / "empty-daily"

        output = inspect.build_daily_report_text(log_dir=empty_dir)

        self.assertIn("HAMMER RADAR DAILY TRADE CANDIDATE REPORT", output)
        self.assertIn(f"archive_log_dir: {empty_dir}", output)
        self.assertIn("total_signals_in_window: 0", output)
        self.assertIn("no candidates in window", output)
        self.assertIn("This is paper/operator guidance only.", output)
        self.assertFalse(empty_dir.exists())

    def test_daily_report_works_with_fixture_records(self) -> None:
        output = inspect.build_daily_report_text(since_hours=10000)

        self.assertIn("1. HEADER", output)
        self.assertIn("2. MARKET/STRATEGY SUMMARY", output)
        self.assertIn("3. PERFORMANCE SUMMARY", output)
        self.assertIn("4. CANDIDATE RANKING", output)
        self.assertIn("5. SAFETY/RISK OUTPUT", output)
        self.assertIn("total_signals_in_window: 1", output)
        self.assertIn("total_outcomes_in_window: 1", output)
        self.assertIn("closed_paper_positions: 1", output)
        self.assertIn("fill_rate: 100.00%", output)

    def test_daily_report_ranks_tradable_bullish_divergence_above_rejected_no_divergence(self) -> None:
        report_dir = Path(self.temp_dir.name) / "daily-ranking"
        good = self._build_signal(
            signal_id="good|1",
            timestamp="2026-04-27T12:00:00+00:00",
            rsi_value=48.0,
            rsi_state="neutral",
            divergence_type="bullish",
            divergence_confirmed=True,
        )
        rejected = self._build_signal(
            signal_id="rejected|1",
            timestamp="2026-04-27T12:01:00+00:00",
            tradable=False,
            reject_reason="bias_not_aligned",
            bias_aligned=False,
            divergence_type=None,
            divergence_confirmed=False,
            hammer_strength=84.0,
        )
        archive.append_signal(good, log_dir=report_dir)
        archive.append_signal(rejected, log_dir=report_dir)

        output = inspect.build_daily_report_text(log_dir=report_dir, since_hours=10000, limit=2)

        self.assertLess(output.index("signal_id: good|1"), output.index("signal_id: rejected|1"))
        self.assertIn("tier: ACTIONABLE_PAPER_CANDIDATE", output)
        self.assertIn("signal_id: good|1", output)
        self.assertIn("signal_id: rejected|1", output)

    def test_daily_report_penalizes_oversold_without_confirmation(self) -> None:
        report_dir = Path(self.temp_dir.name) / "daily-oversold"
        archive.append_signal(
            self._build_signal(
                signal_id="oversold|1",
                timestamp="2026-04-27T12:00:00+00:00",
                rsi_value=21.0,
                rsi_state="oversold",
                divergence_type="bullish",
                divergence_confirmed=False,
            ),
            log_dir=report_dir,
        )

        output = inspect.build_daily_report_text(log_dir=report_dir, since_hours=10000)

        self.assertIn("score: 55", output)
        self.assertIn("tier: CONTEXT_ONLY", output)
        self.assertIn("Avoid for now: oversold bucket has weak forward performance without confirmation.", output)

    def test_daily_report_includes_r9_metadata(self) -> None:
        report_dir = Path(self.temp_dir.name) / "daily-r9"
        archive.append_signal(
            self._build_signal(
                signal_id="r9-daily|1",
                timestamp="2026-04-27T12:00:00+00:00",
                rsi_value=51.25,
                rsi_state="neutral",
                divergence_type="bullish",
                divergence_confirmed=True,
                extreme_trigger=True,
                critical_trigger=True,
            ),
            log_dir=report_dir,
        )

        output = inspect.build_daily_report_text(log_dir=report_dir, since_hours=10000)

        self.assertIn("r9_metadata_coverage_pct: 100.00%", output)
        self.assertIn("total_candidates_with_rsi: 1", output)
        self.assertIn("total_candidates_with_confirmed_divergence: 1", output)
        self.assertIn("total_candidates_with_extreme_or_critical_triggers: 1", output)
        self.assertIn("rsi: 51.2500 state=neutral", output)
        self.assertIn("divergence: type=bullish confirmed=True", output)

    def test_daily_report_respects_env_log_dir(self) -> None:
        env_dir = Path(self.temp_dir.name) / "daily-env"
        archive.append_signal(
            self._build_signal(signal_id="env-daily|1", timestamp="2026-04-27T12:00:00+00:00"),
            log_dir=env_dir,
        )

        with patch.dict("os.environ", {LOG_DIR_ENV_VAR: str(env_dir)}):
            output = inspect.build_daily_report_text(since_hours=10000)

        self.assertIn(f"archive_log_dir: {env_dir}", output)
        self.assertIn("signal_id: env-daily|1", output)

    def test_live_checklist_works_on_empty_archive(self) -> None:
        empty_dir = Path(self.temp_dir.name) / "empty-live"

        output = inspect.build_live_checklist_text(log_dir=empty_dir)

        self.assertIn("HAMMER RADAR MANUAL TINY-LIVE CHECKLIST", output)
        self.assertIn(f"archive_log_dir: {empty_dir}", output)
        self.assertIn("live_execution_enabled: false", output)
        self.assertIn("eligible_tiny_live_count: 0", output)
        self.assertIn("no candidates in window", output)
        self.assertIn("No live order was placed.", output)
        self.assertFalse(empty_dir.exists())

    def test_live_checklist_allows_long_tradable_bullish_neutral_candidate(self) -> None:
        report_dir = Path(self.temp_dir.name) / "live-long"
        archive.append_signal(
            self._build_signal(
                signal_id="live-long|1",
                timestamp="2026-04-27T12:00:00+00:00",
                rsi_value=50.0,
                rsi_state="neutral",
                divergence_type="bullish",
                divergence_confirmed=True,
            ),
            log_dir=report_dir,
        )

        output = inspect.build_live_checklist_text(log_dir=report_dir, since_hours=10000)

        self.assertIn("decision: ELIGIBLE_TINY_LIVE", output)
        self.assertIn("reason: passes conservative manual tiny-live checklist", output)
        self.assertIn("eligible_tiny_live_count: 1", output)
        self.assertIn("live_execution_enabled: false", output)

    def test_live_checklist_keeps_short_paper_only_by_default_unless_allowed(self) -> None:
        report_dir = Path(self.temp_dir.name) / "live-short"
        archive.append_signal(
            self._build_signal(
                signal_id="live-short|1",
                direction="short",
                timestamp="2026-04-27T12:00:00+00:00",
                rsi_value=50.0,
                rsi_state="neutral",
                divergence_type="bearish",
                divergence_confirmed=True,
            ),
            log_dir=report_dir,
        )

        default_output = inspect.build_live_checklist_text(log_dir=report_dir, since_hours=10000)
        allowed_output = inspect.build_live_checklist_text(
            log_dir=report_dir,
            since_hours=10000,
            allow_short=True,
        )

        self.assertIn("decision: PAPER_ONLY", default_output)
        self.assertIn("reason: short candidate requires --allow-short", default_output)
        self.assertIn("decision: ELIGIBLE_TINY_LIVE", allowed_output)

    def test_live_checklist_keeps_oversold_paper_only_by_default_unless_allowed(self) -> None:
        report_dir = Path(self.temp_dir.name) / "live-oversold"
        archive.append_signal(
            self._build_signal(
                signal_id="live-oversold|1",
                timestamp="2026-04-27T12:00:00+00:00",
                rsi_value=21.0,
                rsi_state="oversold",
                divergence_type="bullish",
                divergence_confirmed=True,
            ),
            log_dir=report_dir,
        )

        default_output = inspect.build_live_checklist_text(log_dir=report_dir, since_hours=10000)
        allowed_output = inspect.build_live_checklist_text(
            log_dir=report_dir,
            since_hours=10000,
            allow_oversold=True,
        )

        self.assertIn("decision: PAPER_ONLY", default_output)
        self.assertIn("reason: oversold candidate requires --allow-oversold", default_output)
        self.assertIn("decision: ELIGIBLE_TINY_LIVE", allowed_output)

    def test_live_checklist_forbids_rejected_non_tradable_signal(self) -> None:
        report_dir = Path(self.temp_dir.name) / "live-rejected"
        archive.append_signal(
            self._build_signal(
                signal_id="live-rejected|1",
                timestamp="2026-04-27T12:00:00+00:00",
                tradable=False,
                reject_reason="strength_below_minimum",
                rsi_value=50.0,
                rsi_state="neutral",
                divergence_type="bullish",
                divergence_confirmed=True,
            ),
            log_dir=report_dir,
        )

        output = inspect.build_live_checklist_text(log_dir=report_dir, since_hours=10000)

        self.assertIn("decision: FORBIDDEN", output)
        self.assertIn("reason: not tradable", output)

    def test_live_checklist_forbids_missing_r9_metadata(self) -> None:
        report_dir = Path(self.temp_dir.name) / "live-missing-r9"
        archive.append_signal(
            self._build_signal(signal_id="live-missing-r9|1", timestamp="2026-04-27T12:00:00+00:00"),
            log_dir=report_dir,
        )

        output = inspect.build_live_checklist_text(log_dir=report_dir, since_hours=10000)

        self.assertIn("decision: FORBIDDEN", output)
        self.assertIn("reason: missing R9 metadata", output)

    def test_live_checklist_forbids_missing_stop(self) -> None:
        report_dir = Path(self.temp_dir.name) / "live-missing-stop"
        archive.append_signal(
            self._build_signal(
                signal_id="live-missing-stop|1",
                timestamp="2026-04-27T12:00:00+00:00",
                invalidation=0.0,
                rsi_value=50.0,
                rsi_state="neutral",
                divergence_type="bullish",
                divergence_confirmed=True,
            ),
            log_dir=report_dir,
        )

        output = inspect.build_live_checklist_text(log_dir=report_dir, since_hours=10000)

        self.assertIn("decision: FORBIDDEN", output)
        self.assertIn("reason: missing stop/invalidation", output)

    def test_live_checklist_calculates_risk_distance_and_position_size(self) -> None:
        report_dir = Path(self.temp_dir.name) / "live-risk"
        archive.append_signal(
            self._build_signal(
                signal_id="live-risk|1",
                timestamp="2026-04-27T12:00:00+00:00",
                rsi_value=50.0,
                rsi_state="neutral",
                divergence_type="bullish",
                divergence_confirmed=True,
            ),
            log_dir=report_dir,
        )

        output = inspect.build_live_checklist_text(log_dir=report_dir, since_hours=10000, max_risk_usd=5)

        self.assertIn("estimated_risk_distance_pct: 5.0000%", output)
        self.assertIn("suggested_max_position_size_usd: 100.0000", output)

    @staticmethod
    def _build_signal(
        *,
        signal_id: str = "BTCUSDT|13m|long|2026-04-24T16:27:59.999000+00:00",
        symbol: str = "BTCUSDT",
        timeframe: str = "13m",
        direction: str = "long",
        timestamp: str = "2026-04-24T16:27:59.999000+00:00",
        hammer_strength: float = 95.0,
        invalidation: float = 95.0,
        bias_aligned: bool = True,
        tradable: bool = True,
        reject_reason: str | None = None,
        rsi_value: float | None = None,
        rsi_state: str | None = None,
        divergence_type: str | None = None,
        divergence_confirmed: bool = False,
        extreme_trigger: bool = False,
        critical_trigger: bool = False,
        micro_scalp_candidate: bool = False,
        requires_human_approval: bool = False,
    ) -> SignalRecord:
        return SignalRecord(
            signal_id=signal_id,
            symbol=symbol,
            timeframe=timeframe,
            direction=direction,
            timestamp=timestamp,
            hammer_strength=hammer_strength,
            hammer_high=101.0,
            hammer_low=94.0,
            fib_50=100.5,
            fib_618=100.0,
            fib_650=99.5,
            fib_786=98.5,
            invalidation=invalidation,
            bias_timeframe="4H",
            bias_direction="bullish",
            bias_aligned=bias_aligned,
            same_direction_streak=0,
            opposite_direction_streak=0,
            tradable=tradable,
            reject_reason=reject_reason,
            trend_direction="bullish",
            trend_strength_score=0.4,
            trend_lookback_candles=3,
            ema_4h_20=100.0,
            price_vs_ema_4h_pct=0.1,
            signal_close=100.0,
            rsi_value=rsi_value,
            rsi_state=rsi_state,
            divergence_type=divergence_type,
            divergence_confirmed=divergence_confirmed,
            extreme_trigger=extreme_trigger,
            critical_trigger=critical_trigger,
            micro_scalp_candidate=micro_scalp_candidate,
            requires_human_approval=requires_human_approval,
        )


if __name__ == "__main__":
    unittest.main()
