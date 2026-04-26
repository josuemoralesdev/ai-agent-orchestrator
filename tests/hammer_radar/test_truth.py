from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator import archive, truth, positions
from src.app.hammer_radar.operator.models import OutcomeRecord, SignalRecord
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR


class TruthReportTestCase(unittest.TestCase):
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

        self._seed_setup(
            signal_id_prefix="good",
            direction="long",
            timeframe="13m",
            entry_mode="fib_618",
            pnl_values=(2.0, 1.0, 0.5),
            trend_direction="bullish",
            trend_strength_score=0.6,
            price_vs_ema_4h_pct=0.7,
        )
        self._seed_setup(
            signal_id_prefix="weak",
            direction="short",
            timeframe="55m",
            entry_mode="market_close",
            pnl_values=(-1.0, -2.0, -0.5),
            trend_direction="bearish",
            trend_strength_score=0.6,
            price_vs_ema_4h_pct=-0.7,
        )
        self._seed_setup(
            signal_id_prefix="small",
            direction="long",
            timeframe="13m",
            entry_mode="fib_650",
            pnl_values=(3.0, 2.0),
            trend_direction="bullish",
            trend_strength_score=0.3,
            price_vs_ema_4h_pct=0.1,
        )

    def tearDown(self) -> None:
        archive.LOG_DIR = self.original_archive_log_dir
        archive.SIGNALS_PATH = self.original_signals_path
        archive.OUTCOMES_PATH = self.original_outcomes_path
        positions.LOG_DIR = self.original_positions_log_dir
        positions.POSITIONS_PATH = self.original_positions_path
        positions.POSITION_EVENTS_PATH = self.original_position_events_path
        self.temp_dir.cleanup()

    def test_summary_calculates_group_and_totals(self) -> None:
        output = truth.build_truth_summary_text()

        self.assertIn("HAMMER RADAR TRUTH SUMMARY", output)
        self.assertIn("setup_groups: 3", output)
        self.assertIn("samples: 8", output)
        self.assertIn("fills: 8", output)

    def test_top_setup_ranking_prefers_best_win_rate_and_pnl(self) -> None:
        output = truth.build_top_setups_text(limit=1, min_samples=3)

        self.assertIn("HAMMER RADAR TOP SETUPS", output)
        self.assertIn("entry=fib_618", output)
        self.assertNotIn("entry=market_close", output)

    def test_weak_setup_ranking_prefers_lowest_average_pnl(self) -> None:
        output = truth.build_weak_setups_text(limit=1, min_samples=3)

        self.assertIn("HAMMER RADAR WEAK SETUPS", output)
        self.assertIn("entry=market_close", output)

    def test_min_sample_filter_excludes_small_group(self) -> None:
        output = truth.build_top_setups_text(limit=10, min_samples=3)

        self.assertNotIn("entry=fib_650", output)

    def test_grouped_entry_mode_report_smoke(self) -> None:
        output = truth.build_grouped_truth_text("entry_mode")

        self.assertIn("HAMMER RADAR TRUTH BY ENTRY_MODE", output)
        self.assertIn("fib_618", output)
        self.assertIn("market_close", output)

    def test_truth_reads_alternate_log_dir_fixture(self) -> None:
        alternate_dir = Path(self.temp_dir.name) / "truth-alternate"
        self._seed_setup(
            signal_id_prefix="alternate",
            direction="long",
            timeframe="13m",
            entry_mode="fib_618",
            pnl_values=(1.0,),
            trend_direction="bullish",
            trend_strength_score=0.6,
            price_vs_ema_4h_pct=0.7,
            log_dir=alternate_dir,
        )

        output = truth.build_truth_summary_text(log_dir=alternate_dir)

        self.assertIn("signals: 1", output)
        self.assertIn("outcomes: 1", output)
        self.assertIn("samples: 1", output)

    def test_truth_env_log_dir_override_reads_alternate_fixture(self) -> None:
        alternate_dir = Path(self.temp_dir.name) / "truth-env-alternate"
        self._seed_setup(
            signal_id_prefix="env-alternate",
            direction="long",
            timeframe="13m",
            entry_mode="fib_618",
            pnl_values=(1.0,),
            trend_direction="bullish",
            trend_strength_score=0.6,
            price_vs_ema_4h_pct=0.7,
            log_dir=alternate_dir,
        )

        with patch.dict("os.environ", {LOG_DIR_ENV_VAR: str(alternate_dir)}):
            output = truth.build_truth_summary_text()

        self.assertIn("signals: 1", output)
        self.assertIn("outcomes: 1", output)

    def test_missing_r9_metadata_does_not_crash_group_reports(self) -> None:
        rsi_output = truth.build_rsi_state_truth_text()
        divergence_output = truth.build_divergence_truth_text()
        trigger_output = truth.build_trigger_truth_text()

        self.assertIn("missing", rsi_output)
        self.assertIn("missing", divergence_output)
        self.assertIn("missing", trigger_output)

    def test_grouping_by_rsi_state_works(self) -> None:
        self._seed_setup(
            signal_id_prefix="rsi-oversold",
            direction="long",
            timeframe="13m",
            entry_mode="fib_618",
            pnl_values=(2.0, -1.0),
            trend_direction="bullish",
            trend_strength_score=0.6,
            price_vs_ema_4h_pct=0.7,
            rsi_value=24.0,
            rsi_state="oversold",
        )

        output = truth.build_rsi_state_truth_text()

        self.assertIn("HAMMER RADAR TRUTH BY RSI_STATE", output)
        self.assertIn("oversold", output)
        self.assertIn("samples=2", output)

    def test_grouping_by_divergence_works(self) -> None:
        self._seed_setup(
            signal_id_prefix="div-bull",
            direction="long",
            timeframe="13m",
            entry_mode="fib_618",
            pnl_values=(2.0,),
            trend_direction="bullish",
            trend_strength_score=0.6,
            price_vs_ema_4h_pct=0.7,
            rsi_value=28.0,
            rsi_state="oversold",
            divergence_type="bullish",
            divergence_confirmed=True,
        )

        output = truth.build_divergence_truth_text()

        self.assertIn("HAMMER RADAR TRUTH BY DIVERGENCE", output)
        self.assertIn("type=bullish confirmed=Y", output)

    def test_grouping_by_trigger_flags_works(self) -> None:
        self._seed_setup(
            signal_id_prefix="trigger-extreme",
            direction="long",
            timeframe="13m",
            entry_mode="fib_618",
            pnl_values=(2.0,),
            trend_direction="bullish",
            trend_strength_score=0.6,
            price_vs_ema_4h_pct=0.7,
            rsi_value=18.0,
            rsi_state="extreme_oversold",
            extreme_trigger=True,
            critical_trigger=True,
            micro_scalp_candidate=True,
            requires_human_approval=True,
        )

        output = truth.build_trigger_truth_text()

        self.assertIn("HAMMER RADAR TRUTH BY TRIGGER", output)
        self.assertIn("extreme=Y critical=Y micro_scalp=Y human_approval=Y", output)

    def test_strategy_eligible_smoke(self) -> None:
        output = truth.build_strategy_eligible_text(limit=10, min_samples=3)

        self.assertIn("HAMMER RADAR STRATEGY ELIGIBLE", output)
        self.assertIn("entry=fib_618", output)

    def test_paper_exits_smoke(self) -> None:
        signal = SignalRecord(
            signal_id="paper-exit",
            symbol="BTCUSDT",
            timeframe="13m",
            direction="long",
            timestamp="2026-04-24T16:27:59.999000+00:00",
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
        )
        position = positions.create_paper_position(signal)
        assert position is not None
        positions.close_position(position, exit_price=110.0, close_reason="take_profit", closed_at="2026-04-24T16:42:59.999000+00:00")

        output = truth.build_paper_exits_text()

        self.assertIn("HAMMER RADAR PAPER EXITS", output)
        self.assertIn("reason=take_profit", output)

    def _seed_setup(
        self,
        *,
        signal_id_prefix: str,
        direction: str,
        timeframe: str,
        entry_mode: str,
        pnl_values: tuple[float, ...],
        trend_direction: str,
        trend_strength_score: float,
        price_vs_ema_4h_pct: float,
        log_dir: Path | None = None,
        rsi_value: float | None = None,
        rsi_state: str | None = None,
        divergence_type: str | None = None,
        divergence_confirmed: bool = False,
        extreme_trigger: bool = False,
        critical_trigger: bool = False,
        micro_scalp_candidate: bool = False,
        requires_human_approval: bool = False,
    ) -> None:
        for index, pnl_pct in enumerate(pnl_values, start=1):
            signal_id = f"{signal_id_prefix}|{index}"
            timestamp = f"2026-04-24T16:{index:02d}:59.999000+00:00"
            signal = SignalRecord(
                signal_id=signal_id,
                symbol="BTCUSDT",
                timeframe=timeframe,
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
                bias_direction="bullish" if direction == "long" else "bearish",
                bias_aligned=True,
                same_direction_streak=0,
                opposite_direction_streak=0,
                tradable=True,
                reject_reason=None,
                trend_direction=trend_direction,
                trend_strength_score=trend_strength_score,
                trend_lookback_candles=3,
                ema_4h_20=100.0,
                price_vs_ema_4h_pct=price_vs_ema_4h_pct,
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
            archive.append_signal(signal, log_dir=log_dir)
            archive.append_outcome(
                OutcomeRecord(
                    signal_id=signal.signal_id,
                    symbol=signal.symbol,
                    timeframe=signal.timeframe,
                    direction=signal.direction,
                    timestamp=signal.timestamp,
                    entry_price=100.0,
                    exit_price=100.0 + pnl_pct,
                    fill_status="filled",
                    outcome="win" if pnl_pct > 0 else "loss",
                    mae_pct=abs(pnl_pct) / 2.0,
                    mfe_pct=abs(pnl_pct) + 0.25,
                    pnl_pct=pnl_pct,
                    stop_hit=pnl_pct < 0,
                    evaluated_at=timestamp,
                    entry_mode=entry_mode,
                ),
                log_dir=log_dir,
            )


if __name__ == "__main__":
    unittest.main()
