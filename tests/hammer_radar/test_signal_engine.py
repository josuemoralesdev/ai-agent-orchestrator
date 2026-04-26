from __future__ import annotations

import unittest

import pandas as pd

from src.app.hammer_radar.operator.models import SignalRecord
from src.app.hammer_radar.rsi import build_trigger_metadata, calculate_rsi, classify_rsi_state
from src.app.hammer_radar.signal_engine import extract_signal


class SignalEngineTestCase(unittest.TestCase):
    def test_rsi_values_stay_bounded_between_zero_and_one_hundred(self) -> None:
        close_values = [100, 99, 101, 98, 102, 103, 101, 104, 100, 105, 106, 103, 107, 102, 108, 109, 107]

        rsi = calculate_rsi(pd.Series(close_values), length=14).dropna()

        self.assertFalse(rsi.empty)
        self.assertTrue(((rsi >= 0.0) & (rsi <= 100.0)).all())

    def test_rsi_state_classification_matches_requested_bands(self) -> None:
        self.assertEqual("anomaly_oversold", classify_rsi_state(4))
        self.assertEqual("critical_oversold", classify_rsi_state(7.9))
        self.assertEqual("extreme_oversold", classify_rsi_state(9.9))
        self.assertEqual("oversold", classify_rsi_state(19.9))
        self.assertEqual("neutral", classify_rsi_state(50))
        self.assertEqual("overbought", classify_rsi_state(80))
        self.assertEqual("extreme_overbought", classify_rsi_state(90))
        self.assertEqual("critical_overbought", classify_rsi_state(92))
        self.assertEqual("anomaly_overbought", classify_rsi_state(95))

    def test_bullish_divergence_is_detected_from_fake_candles(self) -> None:
        frame = self._build_divergence_frame(
            closes=[100, 98, 96, 93, 95, 97, 94, 90, 92, 95, 98],
            lows=[101, 99, 97, 92, 94, 96, 93, 89, 91, 94, 97],
            highs=[102, 100, 98, 95, 97, 99, 96, 92, 94, 97, 100],
            bullish_hammer=True,
        )

        signal = extract_signal(frame, "BTCUSDT", timeframe="13m", rsi_length=3)

        self.assertIsNotNone(signal)
        self.assertEqual("bullish", signal["divergence"]["type"])
        self.assertTrue(signal["divergence"]["confirmed"])
        self.assertEqual(92.0, signal["divergence"]["price_pivot_1"])
        self.assertEqual(89.0, signal["divergence"]["price_pivot_2"])
        self.assertLess(signal["divergence"]["rsi_pivot_1"], signal["divergence"]["rsi_pivot_2"])

    def test_bearish_divergence_is_detected_from_fake_candles(self) -> None:
        frame = self._build_divergence_frame(
            closes=[100, 102, 104, 107, 105, 103, 106, 110, 108, 105, 102],
            lows=[99, 101, 103, 106, 104, 102, 105, 109, 107, 104, 101],
            highs=[101, 103, 105, 108, 106, 104, 107, 111, 109, 106, 103],
            bearish_hammer=True,
        )

        signal = extract_signal(frame, "BTCUSDT", timeframe="13m", rsi_length=3)

        self.assertIsNotNone(signal)
        self.assertEqual("bearish", signal["divergence"]["type"])
        self.assertTrue(signal["divergence"]["confirmed"])
        self.assertEqual(108.0, signal["divergence"]["price_pivot_1"])
        self.assertEqual(111.0, signal["divergence"]["price_pivot_2"])
        self.assertGreater(signal["divergence"]["rsi_pivot_1"], signal["divergence"]["rsi_pivot_2"])

    def test_rsi_below_or_equal_eight_on_4m_sets_critical_micro_scalp_and_human_approval(self) -> None:
        metadata = build_trigger_metadata(7.9, "4m")

        self.assertTrue(metadata["extreme_trigger"])
        self.assertTrue(metadata["critical_trigger"])
        self.assertTrue(metadata["micro_scalp_candidate"])
        self.assertTrue(metadata["requires_human_approval"])

    def test_rsi_below_or_equal_ten_sets_extreme_trigger(self) -> None:
        metadata = build_trigger_metadata(9.9, "13m")

        self.assertTrue(metadata["extreme_trigger"])
        self.assertFalse(metadata["critical_trigger"])

    def test_rsi_above_or_equal_ninety_two_on_4m_sets_critical_micro_scalp_and_human_approval(self) -> None:
        metadata = build_trigger_metadata(92.0, "4m")

        self.assertTrue(metadata["extreme_trigger"])
        self.assertTrue(metadata["critical_trigger"])
        self.assertTrue(metadata["micro_scalp_candidate"])
        self.assertTrue(metadata["requires_human_approval"])

    def test_signal_record_serialization_includes_nested_rsi_and_divergence_payloads(self) -> None:
        record = SignalRecord(
            signal_id="BTCUSDT|4m|long|2026-04-24T16:27:59.999000+00:00",
            symbol="BTCUSDT",
            timeframe="4m",
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
            tradable=False,
            rsi_length=14,
            rsi_value=7.9,
            rsi_state="critical_oversold",
            divergence_type="bullish",
            divergence_confirmed=True,
            divergence_price_pivot_1=104250.0,
            divergence_price_pivot_2=103880.0,
            divergence_rsi_pivot_1=17.9,
            divergence_rsi_pivot_2=24.6,
            extreme_trigger=True,
            critical_trigger=True,
            micro_scalp_candidate=True,
            requires_human_approval=True,
        )

        payload = record.to_dict()

        self.assertEqual(14, payload["rsi"]["length"])
        self.assertEqual(7.9, payload["rsi"]["value"])
        self.assertEqual("critical_oversold", payload["rsi"]["state"])
        self.assertEqual("bullish", payload["divergence"]["type"])
        self.assertTrue(payload["divergence"]["confirmed"])
        self.assertTrue(payload["critical_trigger"])
        self.assertTrue(payload["micro_scalp_candidate"])
        self.assertTrue(payload["requires_human_approval"])

    @staticmethod
    def _build_divergence_frame(
        *,
        closes: list[float],
        lows: list[float],
        highs: list[float],
        bullish_hammer: bool = False,
        bearish_hammer: bool = False,
    ) -> pd.DataFrame:
        index = pd.date_range("2026-04-24T16:00:00Z", periods=len(closes), freq="13min")
        frame = pd.DataFrame(
            {
                "open_time": index,
                "close_time": index,
                "open": closes,
                "high": highs,
                "low": lows,
                "close": closes,
                "volume": [1.0] * len(closes),
                "bullish_hammer": [False] * (len(closes) - 1) + [bullish_hammer],
                "bearish_hammer": [False] * (len(closes) - 1) + [bearish_hammer],
                "hammer_strength": [0.0] * (len(closes) - 1) + [95.0],
            }
        )
        return frame


if __name__ == "__main__":
    unittest.main()
