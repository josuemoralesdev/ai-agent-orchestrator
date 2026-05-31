from __future__ import annotations

import json
import subprocess
import sys
import unittest

from src.app.hammer_radar.operator.lane_control import (
    LANE_BLOCKED,
    LANE_DISABLED,
    build_lane_control_status,
    evaluate_lane_permission,
    get_lane_by_tuple,
    load_lane_controls,
    normalize_lane_key,
)
from src.app.hammer_radar.operator.strategy_performance import ELIGIBLE_FOR_FUTURE_TINY_LIVE


class LaneControlTests(unittest.TestCase):
    def test_config_loads(self) -> None:
        controls = load_lane_controls()

        self.assertEqual("1.0", controls["schema_version"])
        self.assertEqual("disabled", controls["default_mode"])
        self.assertEqual(8, len(controls["lanes"]))

    def test_lane_keys_normalize_consistently(self) -> None:
        self.assertEqual(
            "BTCUSDT|13m|long|ladder_close_50_618",
            normalize_lane_key(" btcusdt ", "13M", " LONG ", "LADDER_CLOSE_50_618"),
        )

    def test_initial_lane_modes(self) -> None:
        controls = load_lane_controls()

        self.assertEqual(
            "tiny_live",
            get_lane_by_tuple("BTCUSDT", "13m", "long", "ladder_close_50_618", controls=controls)["mode"],
        )
        self.assertEqual(
            "tiny_live",
            get_lane_by_tuple("BTCUSDT", "44m", "long", "ladder_close_50_618", controls=controls)["mode"],
        )
        self.assertEqual(
            "paper",
            get_lane_by_tuple("BTCUSDT", "8m", "long", "ladder_close_50_618", controls=controls)["mode"],
        )
        self.assertEqual(
            "paper",
            get_lane_by_tuple("BTCUSDT", "4m", "long", "ladder_close_50_618", controls=controls)["mode"],
        )
        self.assertEqual(
            "paper",
            get_lane_by_tuple("BTCUSDT", "4m", "short", "ladder_close_50_618", controls=controls)["mode"],
        )
        self.assertEqual(
            "paper",
            get_lane_by_tuple("BTCUSDT", "8m", "short", "ladder_close_50_618", controls=controls)["mode"],
        )
        self.assertEqual(
            "paper",
            get_lane_by_tuple("BTCUSDT", "13m", "short", "ladder_close_50_618", controls=controls)["mode"],
        )
        self.assertEqual(
            "paper",
            get_lane_by_tuple("BTCUSDT", "44m", "short", "ladder_close_50_618", controls=controls)["mode"],
        )

    def test_unknown_lane_is_disabled(self) -> None:
        payload = evaluate_lane_permission(
            "ETHUSDT",
            "13m",
            "long",
            "ladder_close_50_618",
            live_eligibility_matrix={"recommendations": []},
        )

        self.assertEqual(LANE_DISABLED, payload["status"])
        self.assertEqual("disabled", payload["mode"])

    def test_safety_flags_are_always_false(self) -> None:
        payload = evaluate_lane_permission(
            "BTCUSDT",
            "13m",
            "long",
            "ladder_close_50_618",
            live_eligibility_matrix={"recommendations": []},
        )

        self.assertEqual(
            {
                "order_placed": False,
                "real_order_placed": False,
                "execution_attempted": False,
                "order_payload_created": False,
                "network_allowed": False,
                "secrets_shown": False,
            },
            payload["safety"],
        )

    def test_tiny_live_does_not_bypass_global_gates(self) -> None:
        controls = {
            "lanes": [
                {
                    "lane_key": "BTCUSDT|13m|long|ladder_close_50_618",
                    "symbol": "BTCUSDT",
                    "timeframe": "13m",
                    "direction": "long",
                    "entry_mode": "ladder_close_50_618",
                    "mode": "tiny_live",
                    "max_daily_trades": 1,
                    "max_daily_loss_pct": 0.25,
                    "freshness_seconds": 120,
                    "cooldown_after_loss_minutes": 120,
                    "require_protective_orders": True,
                }
            ],
        }
        controls["lane_map"] = {controls["lanes"][0]["lane_key"]: controls["lanes"][0]}
        matrix = {
            "recommendations": [
                {
                    "timeframe": "13m",
                    "direction": "long",
                    "entry_mode": "ladder_close_50_618",
                    "recommendation": ELIGIBLE_FOR_FUTURE_TINY_LIVE,
                    "sample_count": 50,
                    "win_rate_pct": 60.0,
                    "avg_pnl_pct": 0.2,
                    "total_pnl_pct": 10.0,
                    "blockers": [],
                }
            ]
        }

        payload = evaluate_lane_permission(
            "BTCUSDT",
            "13m",
            "long",
            "ladder_close_50_618",
            controls=controls,
            live_eligibility_matrix=matrix,
            global_gate={"status": "FIRST_LIVE_BLOCKED", "execution_enabled_by_gate": False},
        )

        self.assertEqual(LANE_BLOCKED, payload["status"])
        self.assertIn("global first-live activation gate is not FIRST_LIVE_ACTIVATION_READY", payload["blockers"])
        self.assertFalse(payload["safety"]["order_payload_created"])

    def test_compact_status_omits_giant_recommendation_arrays(self) -> None:
        payload = build_lane_control_status(live_eligibility_matrix={"recommendations": []})

        self.assertEqual(8, payload["configured_lanes_count"])
        self.assertEqual(8, payload["active_lanes_count"])
        self.assertIn("lanes", payload)
        self.assertNotIn("recommendations", payload)

    def test_cli_mode_exists_and_returns_compact_status(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                "logs/hammer_radar_forward",
                "lane-control-status",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        payload = json.loads(result.stdout)
        self.assertEqual(8, payload["configured_lanes_count"])
        self.assertEqual(8, payload["active_lanes_count"])
        self.assertNotIn("recommendations", payload)
        self.assertLess(len(result.stdout), 8000)


if __name__ == "__main__":
    unittest.main()
