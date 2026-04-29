from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from subprocess import run
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.market_intelligence import (
    build_market_intelligence_summary,
    build_market_rankings,
    evaluate_ethbtc_rotation,
    load_market_snapshots,
)
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR


class MarketIntelligenceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict(os.environ, {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=True)
        self.env_patch.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_summary_returns_safety_fields(self) -> None:
        payload = build_market_intelligence_summary(log_dir=self.log_dir)

        self.assertFalse(payload["live_execution_enabled"])
        self.assertFalse(payload["order_placed"])
        self.assertEqual("ETHBTC", payload["key_rotation_pair"])
        self.assertTrue(payload["btc_live_only"])

    def test_use_network_false_does_not_call_network(self) -> None:
        with patch("src.app.hammer_radar.operator.market_intelligence.urllib.request.urlopen") as urlopen:
            payload = build_market_intelligence_summary(use_network=False, log_dir=self.log_dir)

        urlopen.assert_not_called()
        self.assertEqual("FALLBACK_ONLY", payload["market_data_status"])
        self.assertFalse(payload["network_used"])

    def test_network_failure_degrades_without_crash(self) -> None:
        with patch("src.app.hammer_radar.operator.market_intelligence.fetch_ticker", side_effect=OSError("offline")):
            payload = build_market_intelligence_summary(use_network=True, log_dir=self.log_dir)

        self.assertEqual("MARKET_DATA_UNAVAILABLE", payload["market_data_status"])
        self.assertTrue(payload["network_used"])
        self.assertFalse(payload["order_placed"])

    def test_mocked_ticker_data_produces_ranked_symbols(self) -> None:
        with patch("src.app.hammer_radar.operator.market_intelligence.fetch_ticker", side_effect=self._ticker):
            payload = build_market_rankings(use_network=True, limit=20, log_dir=self.log_dir)

        symbols = [record["symbol"] for record in payload["ranked_symbols"]]
        self.assertIn("BTCUSDT", symbols)
        self.assertIn("ETHUSDT", symbols)
        self.assertIn("ETHBTC", symbols)
        eth = next(record for record in payload["ranked_symbols"] if record["symbol"] == "ETHUSDT")
        self.assertEqual("OK", eth["market_data_status"])
        self.assertGreaterEqual(eth["market_intelligence_score"], 100)

    def test_ethbtc_positive_change_returns_leading(self) -> None:
        with patch("src.app.hammer_radar.operator.market_intelligence.fetch_ticker", return_value=self._ticker("ETHBTC", change="2.5")):
            payload = evaluate_ethbtc_rotation(use_network=True, log_dir=self.log_dir)

        self.assertEqual("ETH_LEADING_BTC", payload["rotation_state"])

    def test_ethbtc_negative_change_returns_lagging(self) -> None:
        with patch("src.app.hammer_radar.operator.market_intelligence.fetch_ticker", return_value=self._ticker("ETHBTC", change="-2.5")):
            payload = evaluate_ethbtc_rotation(use_network=True, log_dir=self.log_dir)

        self.assertEqual("ETH_LAGGING_BTC", payload["rotation_state"])

    def test_ethbtc_unavailable_returns_unknown(self) -> None:
        payload = evaluate_ethbtc_rotation(use_network=False, log_dir=self.log_dir)

        self.assertEqual("UNKNOWN", payload["rotation_state"])
        self.assertFalse(payload["order_placed"])

    def test_rankings_include_core_symbols_and_permissions(self) -> None:
        payload = build_market_rankings(log_dir=self.log_dir, limit=20)
        records = {record["symbol"]: record for record in payload["ranked_symbols"]}

        self.assertIn("BTCUSDT", records)
        self.assertIn("ETHBTC", records)
        self.assertIn("ETHUSDT", records)
        live_symbols = [symbol for symbol, record in records.items() if record["live_eligible_symbol"]]
        self.assertEqual(["BTCUSDT"], live_symbols)
        self.assertFalse(records["ETHUSDT"]["live_eligible_symbol"])
        self.assertFalse(records["ETHBTC"]["live_eligible_symbol"])
        self.assertTrue(records["ETHBTC"]["paper_watch_enabled"])

    def test_snapshot_write_and_read(self) -> None:
        payload = build_market_intelligence_summary(write=True, log_dir=self.log_dir)
        records = load_market_snapshots(limit=10, log_dir=self.log_dir)

        self.assertTrue((self.log_dir / "market_intelligence_snapshots.ndjson").exists())
        self.assertEqual(1, len(records))
        self.assertEqual(payload["snapshot_id"], records[0]["snapshot_id"])

    def test_api_market_intelligence_summary_works(self) -> None:
        response = self.client.get("/market-intelligence/summary")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertFalse(payload["live_execution_enabled"])
        self.assertFalse(payload["order_placed"])
        self.assertEqual("ETHBTC", payload["key_rotation_pair"])

    def test_api_market_intelligence_rankings_works(self) -> None:
        response = self.client.get("/market-intelligence/rankings")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertFalse(payload["live_execution_enabled"])
        self.assertIn("BTCUSDT", [record["symbol"] for record in payload["ranked_symbols"]])

    def test_api_market_intelligence_rotation_works(self) -> None:
        response = self.client.get("/market-intelligence/rotation")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("ETHBTC", payload["key_rotation_pair"])
        self.assertEqual("UNKNOWN", payload["rotation_state"])

    def test_cli_market_intelligence_summary_works(self) -> None:
        result = self._run_cli(["market-intelligence-summary", "--limit", "20"])

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("HAMMER RADAR MARKET INTELLIGENCE SUMMARY", result.stdout)
        self.assertIn("key_rotation_pair: ETHBTC", result.stdout)

    def test_cli_market_intelligence_rankings_works(self) -> None:
        result = self._run_cli(["market-intelligence-rankings", "--limit", "20"])

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("HAMMER RADAR MARKET INTELLIGENCE RANKINGS", result.stdout)
        self.assertIn("BTCUSDT", result.stdout)

    def test_cli_ethbtc_rotation_works(self) -> None:
        result = self._run_cli(["ethbtc-rotation"])

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("HAMMER RADAR ETHBTC ROTATION", result.stdout)
        self.assertIn("rotation_state: UNKNOWN", result.stdout)

    def test_ui_contains_market_intelligence_panel(self) -> None:
        response = self.client.get("/ui")

        self.assertEqual(200, response.status_code)
        html = response.text
        self.assertIn("Market Intelligence", html)
        self.assertIn("Public/read-only market data only.", html)
        self.assertIn("BTCUSDT remains the only live-readiness symbol", html)

    def _run_cli(self, args: list[str]):
        return run(
            [".venv/bin/python", "-m", "src.app.hammer_radar.operator.inspect", "--log-dir", str(self.log_dir), *args],
            cwd=Path(__file__).resolve().parents[2],
            check=False,
            capture_output=True,
            text=True,
            env={LOG_DIR_ENV_VAR: str(self.log_dir), "PATH": os.environ.get("PATH", "")},
        )

    @staticmethod
    def _ticker(symbol: str, *, change: str | None = None, **_kwargs) -> dict:
        changes = {
            "BTCUSDT": "3.0",
            "ETHUSDT": "9.5",
            "ETHBTC": "1.5",
        }
        return {
            "symbol": symbol,
            "lastPrice": "100.0",
            "priceChangePercent": change if change is not None else changes.get(symbol, "0.0"),
            "quoteVolume": "25000000",
            "volume": "10000",
            "highPrice": "110.0",
            "lowPrice": "90.0",
        }


if __name__ == "__main__":
    unittest.main()
