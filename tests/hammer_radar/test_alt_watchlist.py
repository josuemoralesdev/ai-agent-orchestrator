from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from subprocess import run
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator.alt_watchlist import (
    HIGH_BETA,
    LIQUID_MAJOR,
    build_watchlist,
    build_watchlist_summary,
)
from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR


class AltWatchlistTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict(os.environ, {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=True)
        self.env_patch.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_watchlist_includes_btc_eth_and_ethbtc(self) -> None:
        records = self._records_by_symbol()

        self.assertIn("BTCUSDT", records)
        self.assertIn("ETHUSDT", records)
        self.assertIn("ETHBTC", records)

    def test_btcusdt_is_core_live_stack(self) -> None:
        record = self._records_by_symbol()["BTCUSDT"]

        self.assertTrue(record["live_eligible_symbol"])
        self.assertEqual("CORE_LIVE", record["category"])
        self.assertEqual("BTC_LIVE_STACK", record["pair_type"])
        self.assertFalse(record["watch_only"])

    def test_ethusdt_is_core_watch_paper_only(self) -> None:
        record = self._records_by_symbol()["ETHUSDT"]

        self.assertFalse(record["live_eligible_symbol"])
        self.assertTrue(record["paper_watch_enabled"])
        self.assertTrue(record["watch_only"])
        self.assertEqual("CORE_WATCH", record["category"])
        self.assertEqual("ETH_PAPER_WATCH", record["current_phase_permission"])

    def test_ethbtc_is_relative_strength_watch_only(self) -> None:
        record = self._records_by_symbol()["ETHBTC"]

        self.assertFalse(record["live_eligible_symbol"])
        self.assertTrue(record["paper_watch_enabled"])
        self.assertTrue(record["watch_only"])
        self.assertEqual("RELATIVE_STRENGTH", record["category"])
        self.assertEqual("BTC_RELATIVE_STRENGTH", record["pair_type"])
        self.assertEqual("RELATIVE_STRENGTH_WATCH", record["current_phase_permission"])
        self.assertIn("ETH strength vs BTC", record["reason"])

    def test_summary_key_pairs(self) -> None:
        summary = build_watchlist_summary(log_dir=self.log_dir)

        self.assertEqual("ETHBTC", summary["key_rotation_pair"])
        self.assertEqual("ETHUSDT", summary["next_promotion_candidate"])
        self.assertTrue(summary["btc_live_only"])
        self.assertEqual(["ETHBTC"], summary["relative_strength_symbols"])

    def test_liquid_majors_are_paper_watch_only(self) -> None:
        payload = build_watchlist(category=LIQUID_MAJOR, limit=0, log_dir=self.log_dir)

        self.assertGreater(payload["watchlist_count"], 0)
        for record in payload["symbols"]:
            self.assertFalse(record["live_eligible_symbol"])
            self.assertTrue(record["paper_watch_enabled"])
            self.assertTrue(record["watch_only"])
            self.assertEqual("ALT_PAPER_WATCH", record["current_phase_permission"])

    def test_high_beta_symbols_are_paper_watch_only(self) -> None:
        payload = build_watchlist(category=HIGH_BETA, limit=0, log_dir=self.log_dir)

        self.assertGreater(payload["watchlist_count"], 0)
        for record in payload["symbols"]:
            self.assertFalse(record["live_eligible_symbol"])
            self.assertTrue(record["paper_watch_enabled"])
            self.assertTrue(record["watch_only"])
            self.assertEqual("ALT_PAPER_WATCH", record["current_phase_permission"])

    def test_api_watchlist_safety_fields(self) -> None:
        response = self.client.get("/watchlist")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertFalse(payload["live_execution_enabled"])
        self.assertFalse(payload["order_placed"])
        self.assertTrue(payload["btc_live_only"])
        self.assertGreaterEqual(payload["watchlist_count"], 19)

    def test_api_watchlist_summary_btc_live_only(self) -> None:
        response = self.client.get("/watchlist/summary")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertFalse(payload["live_execution_enabled"])
        self.assertFalse(payload["order_placed"])
        self.assertTrue(payload["btc_live_only"])
        self.assertEqual("ETHBTC", payload["key_rotation_pair"])
        self.assertEqual("ETHUSDT", payload["next_promotion_candidate"])

    def test_cli_watchlist_works(self) -> None:
        result = run(
            [
                ".venv/bin/python",
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                str(self.log_dir),
                "watchlist",
                "--limit",
                "20",
            ],
            cwd=Path(__file__).resolve().parents[2],
            check=False,
            capture_output=True,
            text=True,
            env={LOG_DIR_ENV_VAR: str(self.log_dir), "PATH": os.environ.get("PATH", "")},
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("HAMMER RADAR ETH / ALT WATCHLIST", result.stdout)
        self.assertIn("ETHBTC", result.stdout)
        self.assertIn("BTC_LIVE_STACK", result.stdout)

    def test_cli_watchlist_summary_works(self) -> None:
        result = run(
            [
                ".venv/bin/python",
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                str(self.log_dir),
                "watchlist-summary",
            ],
            cwd=Path(__file__).resolve().parents[2],
            check=False,
            capture_output=True,
            text=True,
            env={LOG_DIR_ENV_VAR: str(self.log_dir), "PATH": os.environ.get("PATH", "")},
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("HAMMER RADAR ETH / ALT WATCHLIST SUMMARY", result.stdout)
        self.assertIn("key_rotation_pair: ETHBTC", result.stdout)
        self.assertIn("next_promotion_candidate: ETHUSDT", result.stdout)

    def test_ui_contains_alt_watchlist_panel_and_safety_text(self) -> None:
        response = self.client.get("/ui")

        self.assertEqual(200, response.status_code)
        html = response.text
        self.assertIn("ETH / Alt Watchlist", html)
        self.assertIn("BTCUSDT remains the only live-readiness symbol", html)
        self.assertIn("ETHUSDT and ETHBTC are watchlist and paper-only", html)
        self.assertIn("ETHBTC tracks ETH strength vs BTC", html)
        self.assertIn("No alt live tickets", html)
        self.assertIn("No alt live orders", html)

    def _records_by_symbol(self) -> dict[str, dict]:
        payload = build_watchlist(limit=0, log_dir=self.log_dir)
        return {record["symbol"]: record for record in payload["symbols"]}


if __name__ == "__main__":
    unittest.main()
