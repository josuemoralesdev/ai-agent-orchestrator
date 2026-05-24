from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from src.app.hammer_radar.operator.fresh_signal_router import (
    ARMED_DRY_RUN_OBSERVE,
    BLOCKED_BY_LANE,
    EXPIRED_SIGNAL,
    NO_MATCHING_LANE,
    PAPER_OBSERVE,
    ROUTED_TO_LANE,
    TINY_LIVE_BLOCKED_BY_GLOBAL_GATES,
    build_fresh_signal_router_status,
    build_lane_key_from_candidate,
    evaluate_candidate_against_lanes,
    normalize_candidate,
)
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE, load_lane_controls
from src.app.hammer_radar.operator.strategy_performance import ELIGIBLE_FOR_FUTURE_TINY_LIVE


class FreshSignalRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 5, 23, 22, 40, tzinfo=UTC)
        self.matrix = {
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
                },
                {
                    "timeframe": "44m",
                    "direction": "long",
                    "entry_mode": "ladder_close_50_618",
                    "recommendation": "PAPER_ONLY",
                    "sample_count": 10,
                    "win_rate_pct": 40.0,
                    "avg_pnl_pct": 0.1,
                    "total_pnl_pct": 1.0,
                    "blockers": ["paper-only lane"],
                },
            ]
        }

    def test_candidate_normalizes_correctly(self) -> None:
        candidate = normalize_candidate(
            {
                "signal_id": "sig-1",
                "symbol": " btcusdt ",
                "timeframe": "13M",
                "direction": " LONG ",
                "timestamp": "2026-05-23T22:39:30+00:00",
                "score": 101,
                "tier": "ACTIONABLE_PAPER_CANDIDATE",
            }
        )

        self.assertEqual("sig-1", candidate["candidate_id"])
        self.assertEqual("BTCUSDT", candidate["symbol"])
        self.assertEqual("13m", candidate["timeframe"])
        self.assertEqual("long", candidate["direction"])
        self.assertEqual("ladder_close_50_618", candidate["entry_mode"])
        self.assertEqual(101, candidate["score"])

    def test_lane_key_builds_consistently(self) -> None:
        lane_key = build_lane_key_from_candidate(
            {"symbol": "btcusdt", "timeframe": "13M", "direction": "Long", "entry_mode": "LADDER_CLOSE_50_618"}
        )

        self.assertEqual("BTCUSDT|13m|long|ladder_close_50_618", lane_key)

    def test_fresh_candidate_routes_to_matching_13m_armed_dry_run_lane(self) -> None:
        payload = evaluate_candidate_against_lanes(
            self._candidate("13m", generated_at=self.now - timedelta(seconds=30)),
            live_eligibility_matrix=self.matrix,
            now=self.now,
        )

        self.assertEqual(ROUTED_TO_LANE, payload["route_status"])
        self.assertEqual("armed_dry_run", payload["lane_mode"])
        self.assertEqual(ARMED_DRY_RUN_OBSERVE, payload["route_action"])
        self.assertEqual(SAFETY_FALSE, payload["safety"])

    def test_fresh_candidate_routes_to_44m_paper_lane(self) -> None:
        payload = evaluate_candidate_against_lanes(
            self._candidate("44m", generated_at=self.now - timedelta(seconds=60)),
            live_eligibility_matrix=self.matrix,
            now=self.now,
        )

        self.assertEqual(ROUTED_TO_LANE, payload["route_status"])
        self.assertEqual("paper", payload["lane_mode"])
        self.assertEqual(PAPER_OBSERVE, payload["route_action"])

    def test_stale_candidate_returns_expired_signal(self) -> None:
        payload = evaluate_candidate_against_lanes(
            self._candidate("13m", generated_at=self.now - timedelta(seconds=121)),
            live_eligibility_matrix=self.matrix,
            now=self.now,
        )

        self.assertEqual(EXPIRED_SIGNAL, payload["route_status"])
        self.assertEqual("IGNORE", payload["route_action"])

    def test_unknown_lane_returns_no_matching_lane(self) -> None:
        payload = evaluate_candidate_against_lanes(
            self._candidate("13m", symbol="ETHUSDT", generated_at=self.now - timedelta(seconds=30)),
            live_eligibility_matrix=self.matrix,
            now=self.now,
        )

        self.assertEqual(NO_MATCHING_LANE, payload["route_status"])
        self.assertEqual("IGNORE", payload["route_action"])

    def test_disabled_lane_returns_blocked_by_lane(self) -> None:
        controls = load_lane_controls()
        lane = dict(controls["lane_map"]["BTCUSDT|13m|long|ladder_close_50_618"])
        lane["mode"] = "disabled"
        controls = {**controls, "lanes": [lane], "lane_map": {lane["lane_key"]: lane}}

        payload = evaluate_candidate_against_lanes(
            self._candidate("13m", generated_at=self.now - timedelta(seconds=30)),
            controls=controls,
            live_eligibility_matrix=self.matrix,
            now=self.now,
        )

        self.assertEqual(BLOCKED_BY_LANE, payload["route_status"])
        self.assertEqual("disabled", payload["lane_mode"])
        self.assertEqual("LANE_DISABLED", payload["lane_status"])

    def test_tiny_live_lane_does_not_bypass_global_gates(self) -> None:
        controls = load_lane_controls()
        lane = dict(controls["lane_map"]["BTCUSDT|13m|long|ladder_close_50_618"])
        lane["mode"] = "tiny_live"
        controls = {**controls, "lanes": [lane], "lane_map": {lane["lane_key"]: lane}}

        payload = evaluate_candidate_against_lanes(
            self._candidate("13m", generated_at=self.now - timedelta(seconds=30)),
            controls=controls,
            live_eligibility_matrix=self.matrix,
            global_gate={"status": "FIRST_LIVE_BLOCKED", "execution_enabled_by_gate": False},
            now=self.now,
        )

        self.assertEqual(BLOCKED_BY_LANE, payload["route_status"])
        self.assertEqual("tiny_live", payload["lane_mode"])
        self.assertEqual(TINY_LIVE_BLOCKED_BY_GLOBAL_GATES, payload["route_action"])
        self.assertIn("global first-live activation gate is not FIRST_LIVE_ACTIVATION_READY", payload["blockers"])

    def test_safety_flags_are_always_false(self) -> None:
        status = build_fresh_signal_router_status(
            candidates=[self._candidate("13m", generated_at=self.now - timedelta(seconds=30))],
            now=self.now,
            live_eligibility_matrix=self.matrix,
        )

        self.assertEqual(SAFETY_FALSE, status["safety"])
        self.assertEqual(SAFETY_FALSE, status["routed_candidates"][0].get("safety", SAFETY_FALSE))

    def test_cli_mode_exists_and_returns_compact_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "src.app.hammer_radar.operator.inspect",
                    "--log-dir",
                    tmp,
                    "fresh-signal-router-status",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

        payload = json.loads(result.stdout)
        self.assertIn(payload["status"], {"ROUTER_NO_CANDIDATE_SOURCE", "ROUTER_NO_CANDIDATES", "ROUTER_READY"})
        self.assertIn("lane_summary", payload)
        self.assertNotIn("recommendations", result.stdout)
        self.assertLess(len(result.stdout), 8000)

    def _candidate(
        self,
        timeframe: str,
        *,
        symbol: str = "BTCUSDT",
        generated_at: datetime,
    ) -> dict[str, object]:
        return {
            "candidate_id": f"{symbol}|{timeframe}|long|{generated_at.isoformat()}",
            "symbol": symbol,
            "timeframe": timeframe,
            "direction": "long",
            "entry_mode": "ladder_close_50_618",
            "generated_at": generated_at.isoformat(),
        }


if __name__ == "__main__":
    unittest.main()
