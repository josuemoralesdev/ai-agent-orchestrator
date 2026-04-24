from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.app.hammer_radar.operator import archive, truth
from src.app.hammer_radar.operator.models import OutcomeRecord, SignalRecord


class TruthReportTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        log_dir = Path(self.temp_dir.name)
        self.original_archive_log_dir = archive.LOG_DIR
        self.original_signals_path = archive.SIGNALS_PATH
        self.original_outcomes_path = archive.OUTCOMES_PATH
        archive.LOG_DIR = log_dir
        archive.SIGNALS_PATH = log_dir / "signals.ndjson"
        archive.OUTCOMES_PATH = log_dir / "outcomes.ndjson"

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
            )
            archive.append_signal(signal)
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
                )
            )


if __name__ == "__main__":
    unittest.main()
