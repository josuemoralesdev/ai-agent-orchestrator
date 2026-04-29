from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from subprocess import run
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.eth_paper_candidates import (
    build_eth_paper_candidate,
    build_eth_paper_summary,
    load_eth_candidates,
)
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR


class EthPaperCandidatesTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict(os.environ, {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=True)
        self.env_patch.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_candidate_returns_safety_fields_and_eth_is_not_live_eligible(self) -> None:
        record = build_eth_paper_candidate(log_dir=self.log_dir)

        self.assertFalse(record["live_execution_enabled"])
        self.assertFalse(record["order_placed"])
        self.assertFalse(record["live_eligible_symbol"])
        self.assertTrue(record["paper_watch_enabled"])
        self.assertTrue(record["watch_only"])

    def test_rotation_pair_is_ethbtc(self) -> None:
        record = build_eth_paper_candidate(log_dir=self.log_dir)

        self.assertEqual("ETHBTC", record["rotation_pair"])

    def test_fallback_no_network_does_not_fabricate_signal(self) -> None:
        record = build_eth_paper_candidate(use_network=False, log_dir=self.log_dir)

        self.assertIn(record["paper_candidate_status"], {"INSUFFICIENT_DATA", "WATCH_ONLY_CONTEXT"})
        self.assertNotEqual("PAPER_CANDIDATE", record["paper_candidate_status"])

    def test_positive_momentum_and_ethbtc_leading_returns_long_candidate(self) -> None:
        with self._mock_context(change=3.0, rotation_state="ETH_LEADING_BTC"):
            record = build_eth_paper_candidate(use_network=True, log_dir=self.log_dir)

        self.assertEqual("PAPER_CANDIDATE", record["paper_candidate_status"])
        self.assertEqual("ETH_PAPER_CANDIDATE", record["tier"])
        self.assertEqual("long", record["direction"])
        self.assertFalse(record["live_eligible_symbol"])

    def test_negative_momentum_and_ethbtc_lagging_returns_short_watch_context(self) -> None:
        with self._mock_context(change=-3.0, rotation_state="ETH_LAGGING_BTC"):
            record = build_eth_paper_candidate(use_network=True, log_dir=self.log_dir)

        self.assertEqual("WATCH_ONLY_CONTEXT", record["paper_candidate_status"])
        self.assertEqual("ETH_WATCH_ONLY", record["tier"])
        self.assertEqual("short", record["direction"])
        self.assertFalse(record["live_eligible_symbol"])

    def test_unknown_ethbtc_rotation_does_not_create_fake_strong_candidate(self) -> None:
        with self._mock_context(change=3.0, rotation_state="UNKNOWN"):
            record = build_eth_paper_candidate(use_network=True, log_dir=self.log_dir)

        self.assertEqual("WATCH_ONLY_CONTEXT", record["paper_candidate_status"])
        self.assertNotEqual("ETH_PAPER_CANDIDATE", record["tier"])

    def test_write_archives_candidate(self) -> None:
        record = build_eth_paper_candidate(write=True, log_dir=self.log_dir)
        records = load_eth_candidates(limit=10, log_dir=self.log_dir)

        self.assertTrue((self.log_dir / "ethusdt_paper_candidates.ndjson").exists())
        self.assertEqual(1, len(records))
        self.assertEqual(record["candidate_id"], records[0]["candidate_id"])

    def test_candidate_archive_list_works(self) -> None:
        build_eth_paper_candidate(write=True, log_dir=self.log_dir)
        build_eth_paper_candidate(write=True, log_dir=self.log_dir)

        records = load_eth_candidates(limit=50, log_dir=self.log_dir)

        self.assertEqual(2, len(records))

    def test_summary_returns_btc_only_live_warning(self) -> None:
        summary = build_eth_paper_summary(log_dir=self.log_dir)

        self.assertEqual("ETHUSDT", summary["symbol"])
        self.assertEqual("ETHBTC", summary["rotation_pair"])
        self.assertIn("BTCUSDT remains the only live-readiness symbol", summary["warning"])
        self.assertFalse(summary["live_execution_enabled"])

    def test_api_eth_paper_candidate_works(self) -> None:
        response = self.client.get("/eth-paper/candidate")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("ETHUSDT", payload["symbol"])
        self.assertFalse(payload["order_placed"])

    def test_api_eth_paper_candidates_works(self) -> None:
        build_eth_paper_candidate(write=True, log_dir=self.log_dir)

        response = self.client.get("/eth-paper/candidates")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(1, len(payload["candidates"]))
        self.assertFalse(payload["live_execution_enabled"])

    def test_api_eth_paper_summary_works(self) -> None:
        response = self.client.get("/eth-paper/summary")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("ETHUSDT", payload["symbol"])
        self.assertEqual("ETHBTC", payload["rotation_pair"])

    def test_cli_eth_paper_candidate_works(self) -> None:
        result = self._run_cli(["eth-paper-candidate"])

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("HAMMER RADAR ETHUSDT PAPER CANDIDATE", result.stdout)

    def test_cli_eth_paper_candidates_works(self) -> None:
        build_eth_paper_candidate(write=True, log_dir=self.log_dir)

        result = self._run_cli(["eth-paper-candidates"])

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("HAMMER RADAR ETHUSDT PAPER CANDIDATES", result.stdout)

    def test_cli_eth_paper_summary_works(self) -> None:
        result = self._run_cli(["eth-paper-summary"])

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("HAMMER RADAR ETHUSDT PAPER SUMMARY", result.stdout)

    def test_ui_contains_eth_paper_candidate_panel(self) -> None:
        response = self.client.get("/ui")

        self.assertEqual(200, response.status_code)
        html = response.text
        self.assertIn("ETHUSDT Paper Candidate Engine", html)
        self.assertIn("ETHUSDT is paper-only", html)
        self.assertIn("ETHBTC is rotation context only", html)
        self.assertIn("No ETH live tickets. No ETH live orders.", html)

    def _run_cli(self, args: list[str]):
        return run(
            [".venv/bin/python", "-m", "src.app.hammer_radar.operator.inspect", "--log-dir", str(self.log_dir), *args],
            cwd=Path(__file__).resolve().parents[2],
            check=False,
            capture_output=True,
            text=True,
            env={LOG_DIR_ENV_VAR: str(self.log_dir), "PATH": os.environ.get("PATH", "")},
        )

    def _mock_context(self, *, change: float, rotation_state: str):
        market = {
            "market_data_status": "OK",
            "symbols": [
                {
                    "symbol": "ETHUSDT",
                    "market_data_status": "OK",
                    "market_intelligence_score": 92,
                    "momentum_score": 5,
                    "liquidity_score": 10,
                    "last_price": 3200.0,
                    "price_change_percent_24h": change,
                    "quote_volume_24h": 25000000.0,
                }
            ],
        }
        rotation = {
            "rotation_state": rotation_state,
            "ethbtc_change_percent_24h": 1.5 if rotation_state == "ETH_LEADING_BTC" else -1.5,
        }
        return patch.multiple(
            "src.app.hammer_radar.operator.eth_paper_candidates",
            build_market_intelligence_summary=lambda **_kwargs: market,
            evaluate_ethbtc_rotation=lambda **_kwargs: rotation,
        )


if __name__ == "__main__":
    unittest.main()
