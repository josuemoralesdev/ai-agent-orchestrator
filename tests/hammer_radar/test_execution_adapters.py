from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from src.app.hammer_radar.execution import get_execution_adapter, get_execution_mode
from src.app.hammer_radar.execution.binance_stub import BinanceStubAdapter
from src.app.hammer_radar.execution.paper import PaperExecutionAdapter
from src.app.hammer_radar.operator import positions
from src.app.hammer_radar.operator.models import SignalRecord


class ExecutionAdapterBoundaryTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_log_dir = positions.LOG_DIR
        self.original_positions_path = positions.POSITIONS_PATH
        self.original_position_events_path = positions.POSITION_EVENTS_PATH
        self.original_execution_mode = os.environ.get("HAMMER_RADAR_EXECUTION_MODE")
        positions.LOG_DIR = Path(self.temp_dir.name)
        positions.POSITIONS_PATH = positions.LOG_DIR / "positions.ndjson"
        positions.POSITION_EVENTS_PATH = positions.LOG_DIR / "position_events.ndjson"

    def tearDown(self) -> None:
        positions.LOG_DIR = self.original_log_dir
        positions.POSITIONS_PATH = self.original_positions_path
        positions.POSITION_EVENTS_PATH = self.original_position_events_path
        if self.original_execution_mode is None:
            os.environ.pop("HAMMER_RADAR_EXECUTION_MODE", None)
        else:
            os.environ["HAMMER_RADAR_EXECUTION_MODE"] = self.original_execution_mode
        self.temp_dir.cleanup()

    def test_paper_adapter_loads_safely_and_opens_local_position(self) -> None:
        adapter = get_execution_adapter("paper")

        self.assertIsInstance(adapter, PaperExecutionAdapter)
        result = adapter.place_order(self._build_signal())

        self.assertTrue(result.accepted)
        self.assertIsNotNone(result.position)
        self.assertEqual("opened", result.status)
        self.assertEqual(1, len(adapter.get_open_positions()))

    def test_binance_stub_cannot_place_live_orders(self) -> None:
        adapter = get_execution_adapter("binance_stub")

        self.assertIsInstance(adapter, BinanceStubAdapter)
        with self.assertRaises(NotImplementedError):
            adapter.place_order(self._build_signal())

    def test_unknown_execution_mode_fails_closed(self) -> None:
        os.environ["HAMMER_RADAR_EXECUTION_MODE"] = "definitely_not_valid"

        with self.assertRaises(ValueError):
            get_execution_mode()
        with self.assertRaises(ValueError):
            get_execution_adapter("definitely_not_valid")

    @staticmethod
    def _build_signal() -> SignalRecord:
        return SignalRecord(
            signal_id="BTCUSDT|13m|long|2026-04-24T16:27:59.999000+00:00",
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


if __name__ == "__main__":
    unittest.main()
