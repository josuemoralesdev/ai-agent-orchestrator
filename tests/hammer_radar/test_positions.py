from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.app.hammer_radar.operator.models import SignalRecord
from src.app.hammer_radar.operator import positions


class PaperPositionsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_log_dir = positions.LOG_DIR
        self.original_positions_path = positions.POSITIONS_PATH
        self.original_position_events_path = positions.POSITION_EVENTS_PATH
        positions.LOG_DIR = Path(self.temp_dir.name)
        positions.POSITIONS_PATH = positions.LOG_DIR / "positions.ndjson"
        positions.POSITION_EVENTS_PATH = positions.LOG_DIR / "position_events.ndjson"

    def tearDown(self) -> None:
        positions.LOG_DIR = self.original_log_dir
        positions.POSITIONS_PATH = self.original_positions_path
        positions.POSITION_EVENTS_PATH = self.original_position_events_path
        self.temp_dir.cleanup()

    def test_create_paper_position_is_idempotent_for_signal_entry_pair(self) -> None:
        signal = self._build_signal(tradable=True)

        first_position = positions.create_paper_position(signal)
        duplicate_position = positions.create_paper_position(signal)

        self.assertIsNotNone(first_position)
        self.assertIsNone(duplicate_position)
        self.assertEqual(1, len(positions.load_open_positions()))
        self.assertEqual(1, len(positions.load_position_events()))

    def test_long_position_closes_when_latest_candle_hits_stop(self) -> None:
        signal = self._build_signal(direction="long", tradable=True, fib_618=100.0, invalidation=95.0)
        position = positions.create_paper_position(signal)
        assert position is not None

        closed = positions.evaluate_open_positions(
            [position],
            {
                "13m": {
                    "high": 101.0,
                    "low": 94.0,
                    "open": 100.5,
                    "close": 95.5,
                    "timestamp": "2026-04-24T16:42:59.999000+00:00",
                }
            },
        )

        self.assertEqual(1, len(closed))
        self.assertEqual("closed", closed[0].status)
        self.assertEqual("stop", closed[0].close_reason)
        self.assertAlmostEqual(-5.0, closed[0].pnl_pct)
        self.assertAlmostEqual(-5.0, closed[0].pnl_usd)
        self.assertEqual(0, len(positions.load_open_positions()))
        self.assertEqual(1, len(positions.load_closed_positions()))
        self.assertEqual(2, len(positions.load_position_events()))

    def test_long_position_closes_on_take_profit(self) -> None:
        signal = self._build_signal(direction="long", tradable=True, fib_618=100.0, invalidation=95.0)
        position = positions.create_paper_position(signal)
        assert position is not None

        closed = positions.evaluate_open_positions(
            [position],
            {
                "13m": {
                    "high": 111.0,
                    "low": 99.0,
                    "open": 100.5,
                    "close": 110.5,
                    "timestamp": "2026-04-24T16:42:59.999000+00:00",
                }
            },
        )

        self.assertEqual(1, len(closed))
        self.assertEqual("take_profit", closed[0].close_reason)
        self.assertAlmostEqual(110.0, closed[0].exit_price)

    def test_short_position_closes_on_take_profit(self) -> None:
        signal = self._build_signal(
            direction="short",
            tradable=True,
            fib_618=100.0,
            invalidation=105.0,
            signal_id="BTCUSDT|13m|short|2026-04-24T16:27:59.999000+00:00",
        )
        position = positions.create_paper_position(signal)
        assert position is not None

        closed = positions.evaluate_open_positions(
            [position],
            {
                "13m": {
                    "high": 101.0,
                    "low": 89.0,
                    "open": 99.5,
                    "close": 90.0,
                    "timestamp": "2026-04-24T16:42:59.999000+00:00",
                }
            },
        )

        self.assertEqual(1, len(closed))
        self.assertEqual("take_profit", closed[0].close_reason)
        self.assertAlmostEqual(90.0, closed[0].exit_price)

    def test_stop_wins_over_take_profit_when_both_hit_same_candle(self) -> None:
        signal = self._build_signal(direction="long", tradable=True, fib_618=100.0, invalidation=95.0)
        position = positions.create_paper_position(signal)
        assert position is not None

        closed = positions.evaluate_open_positions(
            [position],
            {
                "13m": {
                    "high": 111.0,
                    "low": 94.0,
                    "open": 100.5,
                    "close": 106.0,
                    "timestamp": "2026-04-24T16:42:59.999000+00:00",
                }
            },
        )

        self.assertEqual(1, len(closed))
        self.assertEqual("stop", closed[0].close_reason)
        self.assertAlmostEqual(95.0, closed[0].exit_price)

    def test_max_hold_close(self) -> None:
        signal = self._build_signal(direction="long", tradable=True, fib_618=100.0, invalidation=95.0)
        position = positions.create_paper_position(signal)
        assert position is not None

        closed = positions.evaluate_open_positions(
            [position],
            {
                "13m": {
                    "high": 104.0,
                    "low": 99.0,
                    "open": 100.0,
                    "close": 103.0,
                    "timestamp": "2026-04-24T17:06:59.999000+00:00",
                }
            },
        )

        self.assertEqual(1, len(closed))
        self.assertEqual("max_hold", closed[0].close_reason)
        self.assertAlmostEqual(103.0, closed[0].exit_price)
        self.assertEqual(3, closed[0].held_candles)

    def test_short_position_stays_open_until_stop_is_hit(self) -> None:
        signal = self._build_signal(
            direction="short",
            tradable=True,
            fib_618=100.0,
            invalidation=103.0,
            signal_id="BTCUSDT|13m|short|2026-04-24T16:27:59.999000+00:00",
            timestamp="2026-04-24T16:27:59.999000+00:00",
        )
        position = positions.create_paper_position(signal)
        assert position is not None

        still_open = positions.evaluate_open_positions(
            [position],
            {
                "13m": {
                    "high": 102.5,
                    "low": 99.0,
                    "open": 100.1,
                    "close": 99.4,
                    "timestamp": "2026-04-24T16:42:59.999000+00:00",
                }
            },
        )

        self.assertEqual([], still_open)
        self.assertEqual(1, len(positions.load_open_positions()))

    def test_backward_compatibility_without_take_profit_fields(self) -> None:
        positions.append_position(
            positions.PaperPosition.from_dict(
                {
                    "position_id": "legacy|fib_618",
                    "signal_id": "legacy",
                    "symbol": "BTCUSDT",
                    "timeframe": "13m",
                    "direction": "long",
                    "entry_mode": "fib_618",
                    "entry_price": 100.0,
                    "size_usd": 100.0,
                    "stop_price": 95.0,
                    "status": "open",
                    "opened_at": "2026-04-24T16:27:59.999000+00:00",
                }
            )
        )

        loaded = positions.load_open_positions()

        self.assertEqual(1, len(loaded))
        self.assertIsNone(loaded[0].take_profit_price)
        self.assertEqual(0, loaded[0].held_candles)

    @staticmethod
    def _build_signal(
        *,
        direction: str = "long",
        tradable: bool = True,
        fib_618: float = 100.0,
        invalidation: float = 95.0,
        signal_id: str = "BTCUSDT|13m|long|2026-04-24T16:27:59.999000+00:00",
        timestamp: str = "2026-04-24T16:27:59.999000+00:00",
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
            fib_618=fib_618,
            fib_650=99.5,
            fib_786=98.5,
            invalidation=invalidation,
            bias_timeframe="4H",
            bias_direction="bullish",
            bias_aligned=True,
            same_direction_streak=0,
            opposite_direction_streak=0,
            tradable=tradable,
            reject_reason=None,
            trend_direction="bullish",
            trend_strength_score=0.4,
            trend_lookback_candles=3,
            ema_4h_20=100.0,
            price_vs_ema_4h_pct=0.1,
            signal_close=100.0,
        )


if __name__ == "__main__":
    unittest.main()
