from __future__ import annotations

import os
import unittest

from src.app.hammer_radar.execution.safety import (
    DEFAULT_ALLOWED_SYMBOLS,
    DEFAULT_EXECUTION_MODE,
    build_safety_check_text,
    evaluate_live_readiness,
    load_execution_safety_config,
)


class ExecutionSafetyTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.original_env = {
            key: os.environ.get(key)
            for key in (
                "HAMMER_RADAR_EXECUTION_MODE",
                "HAMMER_RADAR_LIVE_TRADING_ENABLED",
                "HAMMER_RADAR_MAX_RISK_USD",
                "HAMMER_RADAR_MAX_POSITION_SIZE_USD",
                "HAMMER_RADAR_MAX_OPEN_POSITIONS",
                "HAMMER_RADAR_ALLOWED_SYMBOLS",
                "HAMMER_RADAR_REQUIRE_OPERATOR_APPROVAL",
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

    def test_defaults_are_safe(self) -> None:
        config = load_execution_safety_config()

        self.assertEqual(DEFAULT_EXECUTION_MODE, config.execution_mode)
        self.assertFalse(config.live_trading_enabled)
        self.assertEqual(0.0, config.max_risk_usd)
        self.assertEqual(100.0, config.max_position_size_usd)
        self.assertEqual(1, config.max_open_positions)
        self.assertEqual(DEFAULT_ALLOWED_SYMBOLS, config.allowed_symbols)
        self.assertTrue(config.require_operator_approval)

    def test_paper_mode_readiness_passes(self) -> None:
        readiness = evaluate_live_readiness(load_execution_safety_config())

        self.assertEqual("READY_FOR_PAPER", readiness.verdict)
        self.assertEqual((), readiness.reasons)

    def test_binance_stub_readiness_is_stub_only(self) -> None:
        os.environ["HAMMER_RADAR_EXECUTION_MODE"] = "binance_stub"

        readiness = evaluate_live_readiness(load_execution_safety_config())

        self.assertEqual("READY_FOR_STUB_ONLY", readiness.verdict)

    def test_unsafe_live_config_fails_closed(self) -> None:
        os.environ["HAMMER_RADAR_EXECUTION_MODE"] = "binance_live"
        os.environ["HAMMER_RADAR_LIVE_TRADING_ENABLED"] = "true"
        os.environ["HAMMER_RADAR_MAX_RISK_USD"] = "0"

        with self.assertRaises(ValueError):
            load_execution_safety_config()

    def test_unknown_mode_fails_closed(self) -> None:
        os.environ["HAMMER_RADAR_EXECUTION_MODE"] = "something_else"

        with self.assertRaises(ValueError):
            load_execution_safety_config()

    def test_safety_check_output_mentions_disabled_live_trading(self) -> None:
        output = build_safety_check_text()

        self.assertIn("HAMMER RADAR SAFETY CHECK", output)
        self.assertIn("execution_mode: paper", output)
        self.assertIn("live_trading_enabled: false", output)
        self.assertIn("final_readiness_verdict: READY_FOR_PAPER", output)


if __name__ == "__main__":
    unittest.main()
