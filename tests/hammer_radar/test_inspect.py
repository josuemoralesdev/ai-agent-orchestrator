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

    @staticmethod
    def _build_signal(
        *,
        signal_id: str = "BTCUSDT|13m|long|2026-04-24T16:27:59.999000+00:00",
        direction: str = "long",
        timestamp: str = "2026-04-24T16:27:59.999000+00:00",
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
            symbol="BTCUSDT",
            timeframe="13m",
            direction=direction,
            timestamp=timestamp,
            hammer_strength=95.0,
            hammer_high=101.0,
            hammer_low=94.0,
            fib_50=100.5,
            fib_618=100.0,
            fib_650=99.5,
            fib_786=98.5,
            invalidation=95.0,
            bias_timeframe="4H",
            bias_direction="bullish",
            bias_aligned=True,
            same_direction_streak=0,
            opposite_direction_streak=0,
            tradable=True,
            reject_reason=None,
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
