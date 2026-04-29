from __future__ import annotations

import os
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from subprocess import run
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator import archive
from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.models import SignalRecord
from src.app.hammer_radar.operator.multi_symbol_scanner import (
    ROTATION_CONTEXT,
    build_multi_symbol_summary,
    load_scan_records,
    scan_watchlist,
)
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR


class MultiSymbolScannerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict(os.environ, {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=True)
        self.env_patch.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_scanner_includes_all_r30_watchlist_symbols(self) -> None:
        payload = scan_watchlist(limit=0, log_dir=self.log_dir)

        self.assertEqual(19, payload["scanned_symbols"])
        self.assertEqual(19, len(payload["records"]))

    def test_scanner_includes_btc_eth_and_ethbtc(self) -> None:
        records = self._records_by_symbol()

        self.assertIn("BTCUSDT", records)
        self.assertIn("ETHUSDT", records)
        self.assertIn("ETHBTC", records)

    def test_ethbtc_has_rotation_context_and_is_not_live_eligible(self) -> None:
        record = self._records_by_symbol()["ETHBTC"]

        self.assertEqual(ROTATION_CONTEXT, record["rotation_context"])
        self.assertFalse(record["live_eligible_symbol"])
        self.assertTrue(record["paper_watch_enabled"])
        self.assertTrue(record["watch_only"])
        self.assertEqual("BTC_RELATIVE_STRENGTH", record["pair_type"])

    def test_ethusdt_remains_not_live_eligible(self) -> None:
        record = self._records_by_symbol()["ETHUSDT"]

        self.assertFalse(record["live_eligible_symbol"])
        self.assertTrue(record["paper_watch_enabled"])
        self.assertTrue(record["watch_only"])

    def test_btcusdt_remains_only_live_eligible_symbol(self) -> None:
        records = self._records_by_symbol()
        live_symbols = [symbol for symbol, record in records.items() if record["live_eligible_symbol"]]

        self.assertEqual(["BTCUSDT"], live_symbols)

    def test_scan_preview_does_not_write_archive(self) -> None:
        payload = scan_watchlist(limit=20, write=False, log_dir=self.log_dir)

        self.assertEqual(19, payload["scanned_symbols"])
        self.assertFalse((self.log_dir / "multi_symbol_paper_scans.ndjson").exists())

    def test_scan_write_creates_ndjson(self) -> None:
        payload = scan_watchlist(limit=20, write=True, log_dir=self.log_dir)
        records = load_scan_records(limit=0, log_dir=self.log_dir)

        self.assertTrue((self.log_dir / "multi_symbol_paper_scans.ndjson").exists())
        self.assertEqual(payload["scanned_symbols"], len(records))
        self.assertGreater(len(records), 0)

    def test_scan_records_include_safety_fields(self) -> None:
        record = scan_watchlist(limit=1, log_dir=self.log_dir)["records"][0]

        self.assertFalse(record["live_execution_enabled"])
        self.assertFalse(record["order_placed"])

    def test_archived_signal_creates_paper_candidate_without_live_promotion(self) -> None:
        archive.append_signal(self._signal(symbol="ETHUSDT", signal_id="ETHUSDT|paper|1"), log_dir=self.log_dir)

        record = self._records_by_symbol()["ETHUSDT"]

        self.assertEqual("PAPER_CANDIDATE", record["paper_signal_status"])
        self.assertEqual(1, record["recent_signal_count"])
        self.assertEqual(1, record["recent_tradable_count"])
        self.assertFalse(record["live_eligible_symbol"])

    def test_api_multi_symbol_scan_safety_fields(self) -> None:
        response = self.client.get("/multi-symbol/scan?limit=20&write=false")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertFalse(payload["live_execution_enabled"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["write"])
        self.assertEqual(19, payload["scanned_symbols"])

    def test_api_multi_symbol_scans_lists_archived_records(self) -> None:
        scan_watchlist(limit=3, write=True, log_dir=self.log_dir)

        response = self.client.get("/multi-symbol/scans?limit=20")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertFalse(payload["live_execution_enabled"])
        self.assertFalse(payload["order_placed"])
        self.assertEqual(3, payload["archived_records"])
        self.assertEqual(3, len(payload["records"]))

    def test_api_multi_symbol_summary_key_rotation_pair(self) -> None:
        response = self.client.get("/multi-symbol/summary")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertFalse(payload["live_execution_enabled"])
        self.assertFalse(payload["order_placed"])
        self.assertEqual("ETHBTC", payload["key_rotation_pair"])
        self.assertEqual("ETHUSDT", payload["next_promotion_candidate"])
        self.assertTrue(payload["btc_live_only"])

    def test_cli_multi_symbol_scan_works(self) -> None:
        result = self._run_cli(["multi-symbol-scan", "--limit", "20"])

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("HAMMER RADAR MULTI-SYMBOL PAPER SCAN", result.stdout)
        self.assertIn("ETHBTC", result.stdout)

    def test_cli_multi_symbol_scans_works(self) -> None:
        scan_watchlist(limit=2, write=True, log_dir=self.log_dir)

        result = self._run_cli(["multi-symbol-scans", "--limit", "20"])

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("HAMMER RADAR MULTI-SYMBOL PAPER SCANS", result.stdout)
        self.assertIn("archived_records: 2", result.stdout)

    def test_cli_multi_symbol_summary_works(self) -> None:
        result = self._run_cli(["multi-symbol-summary"])

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("HAMMER RADAR MULTI-SYMBOL PAPER SUMMARY", result.stdout)
        self.assertIn("key_rotation_pair: ETHBTC", result.stdout)

    def test_ui_contains_multi_symbol_scanner_panel_and_safety_text(self) -> None:
        response = self.client.get("/ui")

        self.assertEqual(200, response.status_code)
        html = response.text
        self.assertIn("Multi-Symbol Paper Scanner", html)
        self.assertIn("Paper/watch-only. No alt live tickets.", html)
        self.assertIn("ETHBTC is a rotation compass", html)
        self.assertIn("BTCUSDT remains the only live-readiness symbol", html)

    def test_summary_reports_expected_static_fields(self) -> None:
        summary = build_multi_symbol_summary(log_dir=self.log_dir)

        self.assertEqual(19, summary["total_watchlist_symbols"])
        self.assertEqual(19, summary["scanned_symbols"])
        self.assertEqual(["BTCUSDT"], summary["live_eligible_symbols"])
        self.assertEqual(["ETHBTC"], summary["relative_strength_symbols"])
        self.assertEqual("multi-symbol scanner is paper/watch-only", summary["warning"])

    def _records_by_symbol(self) -> dict[str, dict]:
        payload = scan_watchlist(limit=0, log_dir=self.log_dir)
        return {record["symbol"]: record for record in payload["records"]}

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
    def _signal(*, symbol: str, signal_id: str) -> SignalRecord:
        return SignalRecord(
            signal_id=signal_id,
            symbol=symbol,
            timeframe="13m",
            direction="long",
            timestamp=(datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
            hammer_strength=100.0,
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
            rsi_value=50.0,
            rsi_state="neutral",
            divergence_type="bullish",
            divergence_confirmed=True,
        )


if __name__ == "__main__":
    unittest.main()
