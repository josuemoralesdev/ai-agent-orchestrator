from __future__ import annotations

import os
import unittest

from src.app.hammer_radar.operator.gate import decide_trade_candidate
from src.app.hammer_radar.operator.models import SignalRecord
from src.app.hammer_radar.operator.strategy_config import (
    SUPPORTED_TIMEFRAME_LABELS,
    TIMEFRAME_CONFIGS,
    filter_summary_rows_for_strategy,
    load_strategy_config,
)


class StrategyConfigTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.original_env = {
            key: os.environ.get(key)
            for key in (
                "HAMMER_RADAR_ENABLED_TIMEFRAMES",
                "HAMMER_RADAR_MINIMUM_HAMMER_STRENGTH",
                "HAMMER_RADAR_REQUIRE_BIAS_ALIGNMENT",
                "HAMMER_RADAR_ALLOWED_ENTRY_MODES",
                "HAMMER_RADAR_BLOCKED_ENTRY_MODES",
                "HAMMER_RADAR_MAX_RECENT_SAME_DIRECTION_GAP",
                "HAMMER_RADAR_PAPER_ENABLED",
            )
        }
        for key in self.original_env:
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        for key, value in self.original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_existing_13m_behavior_still_works(self) -> None:
        tradable, reject_reason = decide_trade_candidate(self._build_signal(timeframe="13m"), [])

        self.assertTrue(tradable)
        self.assertIsNone(reject_reason)

    def test_55m_can_be_strategy_eligible_when_config_allows_it(self) -> None:
        tradable, reject_reason = decide_trade_candidate(self._build_signal(timeframe="55m"), [])

        self.assertTrue(tradable)
        self.assertIsNone(reject_reason)

    def test_666m_can_be_strategy_eligible_when_config_allows_it(self) -> None:
        tradable, reject_reason = decide_trade_candidate(self._build_signal(timeframe="666m"), [])

        self.assertTrue(tradable)
        self.assertIsNone(reject_reason)

    def test_4h_can_be_strategy_eligible_when_config_allows_it(self) -> None:
        tradable, reject_reason = decide_trade_candidate(self._build_signal(timeframe="4H"), [])

        self.assertTrue(tradable)
        self.assertIsNone(reject_reason)

    def test_13h_and_13d_labels_are_recognized(self) -> None:
        config = load_strategy_config()

        self.assertIn("13H", SUPPORTED_TIMEFRAME_LABELS)
        self.assertIn("13D", SUPPORTED_TIMEFRAME_LABELS)
        self.assertIn(("13h", "13H"), TIMEFRAME_CONFIGS)
        self.assertIn(("13D", "13D"), TIMEFRAME_CONFIGS)
        self.assertIn("13H", config.enabled_timeframes)
        self.assertIn("13D", config.enabled_timeframes)

    def test_disabled_timeframe_is_rejected(self) -> None:
        os.environ["HAMMER_RADAR_ENABLED_TIMEFRAMES"] = "13m"

        tradable, reject_reason = decide_trade_candidate(self._build_signal(timeframe="55m"), [])

        self.assertFalse(tradable)
        self.assertEqual("timeframe_not_enabled", reject_reason)

    def test_minimum_strength_is_enforced(self) -> None:
        os.environ["HAMMER_RADAR_MINIMUM_HAMMER_STRENGTH"] = "90"

        tradable, reject_reason = decide_trade_candidate(self._build_signal(timeframe="13m", hammer_strength=89.5), [])

        self.assertFalse(tradable)
        self.assertEqual("strength_below_minimum", reject_reason)

    def test_bias_requirement_is_enforced(self) -> None:
        tradable, reject_reason = decide_trade_candidate(self._build_signal(timeframe="13m", bias_aligned=False), [])

        self.assertFalse(tradable)
        self.assertEqual("bias_not_aligned", reject_reason)

    def test_strategy_filter_blocks_disallowed_entry_modes_in_truth_rows(self) -> None:
        rows = [
            {
                "timeframe": "55m",
                "direction": "long",
                "bias_aligned": True,
                "strength_band": "90-100",
                "trend_direction": "bullish",
                "trend_strength_band": "medium",
                "price_vs_ema_4h_pct_band": "near_zero",
                "entry_mode": "market_close",
                "samples": 5,
                "fills": 5,
                "wins": 3,
                "losses": 2,
                "stops": 1,
                "win_rate_on_filled": 60.0,
                "avg_pnl_pct": 0.1,
                "avg_mae_pct": 0.2,
                "avg_mfe_pct": 0.3,
            }
        ]
        os.environ["HAMMER_RADAR_BLOCKED_ENTRY_MODES"] = "market_close"

        filtered = filter_summary_rows_for_strategy(rows)

        self.assertEqual([], filtered)

    @staticmethod
    def _build_signal(
        *,
        timeframe: str,
        hammer_strength: float = 95.0,
        bias_aligned: bool = True,
    ) -> SignalRecord:
        timestamp = "2026-04-24T16:27:59.999000+00:00"
        return SignalRecord(
            signal_id=f"BTCUSDT|{timeframe}|long|{timestamp}",
            symbol="BTCUSDT",
            timeframe=timeframe,
            direction="long",
            timestamp=timestamp,
            hammer_strength=hammer_strength,
            hammer_high=101.0,
            hammer_low=94.0,
            fib_50=100.5,
            fib_618=100.0,
            fib_650=99.5,
            fib_786=98.5,
            invalidation=95.0,
            bias_timeframe="4H",
            bias_direction="bullish",
            bias_aligned=bias_aligned,
            same_direction_streak=0,
            opposite_direction_streak=0,
            tradable=False,
            reject_reason=None,
            trend_direction="bullish",
            trend_strength_score=0.4,
            trend_lookback_candles=3,
            ema_4h_20=100.0,
            price_vs_ema_4h_pct=0.1,
            signal_close=100.0,
        )
