from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from subprocess import run
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.eth_paper_candidates import append_eth_candidate
from src.app.hammer_radar.operator.eth_paper_outcomes import (
    build_eth_paper_outcome,
    build_eth_paper_outcome_summary,
    build_outcome_from_candidate,
    load_eth_paper_outcomes,
)
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR


class EthPaperOutcomesTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict(os.environ, {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=True)
        self.env_patch.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_outcome_returns_safety_fields_and_eth_is_not_live_eligible(self) -> None:
        self._append_candidate(self._candidate(paper_status="PAPER_CANDIDATE", tier="ETH_PAPER_CANDIDATE"))

        record = build_eth_paper_outcome(log_dir=self.log_dir)

        self.assertFalse(record["live_execution_enabled"])
        self.assertFalse(record["order_placed"])
        self.assertFalse(record["live_eligible_symbol"])
        self.assertTrue(record["paper_watch_enabled"])
        self.assertTrue(record["watch_only"])

    def test_rotation_pair_is_ethbtc(self) -> None:
        self._append_candidate(self._candidate())

        record = build_eth_paper_outcome(log_dir=self.log_dir)

        self.assertEqual("ETHBTC", record["rotation_pair"])

    def test_no_candidates_returns_safe_empty_no_data_summary(self) -> None:
        record = build_eth_paper_outcome(log_dir=self.log_dir)
        summary = build_eth_paper_outcome_summary(log_dir=self.log_dir)

        self.assertFalse(record["outcome_created"])
        self.assertEqual("ETH_PAPER_NO_DATA", record["outcome_status"])
        self.assertEqual(0, summary["total_outcomes"])
        self.assertIn("Archive an ETHUSDT paper candidate", summary["next_required_action"])

    def test_insufficient_data_candidate_does_not_fabricate_win_or_loss(self) -> None:
        self._append_candidate(self._candidate(paper_status="INSUFFICIENT_DATA", tier="ETH_INSUFFICIENT_DATA"))

        record = build_eth_paper_outcome(log_dir=self.log_dir)

        self.assertIn(record["outcome_status"], {"ETH_PAPER_NO_DATA", "ETH_PAPER_NO_SIGNAL"})
        self.assertNotIn(record["outcome_status"], {"ETH_PAPER_WIN", "ETH_PAPER_LOSS"})

    def test_paper_candidate_with_last_price_creates_deterministic_levels(self) -> None:
        record = build_outcome_from_candidate(
            self._candidate(
                direction="long",
                last_price=3200.0,
                paper_status="PAPER_CANDIDATE",
                tier="ETH_PAPER_CANDIDATE",
            )
        )

        self.assertEqual(3200.0, record["entry_price"])
        self.assertEqual(3184.0, record["stop_price"])
        self.assertEqual(3216.0, record["take_profit_price"])
        self.assertEqual("ETH_PAPER_UNRESOLVED", record["outcome_status"])

    def test_long_candidate_levels_are_entry_stop_and_take_profit(self) -> None:
        record = build_outcome_from_candidate(self._candidate(direction="long", last_price=100.0))

        self.assertEqual(100.0, record["entry_price"])
        self.assertEqual(99.5, record["stop_price"])
        self.assertEqual(100.5, record["take_profit_price"])

    def test_short_candidate_levels_are_entry_stop_and_take_profit(self) -> None:
        record = build_outcome_from_candidate(self._candidate(direction="short", last_price=100.0))

        self.assertEqual(100.0, record["entry_price"])
        self.assertEqual(100.5, record["stop_price"])
        self.assertEqual(99.5, record["take_profit_price"])

    def test_write_archives_outcome(self) -> None:
        self._append_candidate(self._candidate())

        record = build_eth_paper_outcome(write=True, log_dir=self.log_dir)
        records = load_eth_paper_outcomes(limit=10, log_dir=self.log_dir)

        self.assertTrue((self.log_dir / "ethusdt_paper_outcomes.ndjson").exists())
        self.assertEqual(1, len(records))
        self.assertEqual(record["outcome_id"], records[0]["outcome_id"])

    def test_outcome_archive_list_works(self) -> None:
        self._append_candidate(self._candidate(candidate_id="ethpc_one"))
        build_eth_paper_outcome(write=True, log_dir=self.log_dir)
        self._append_candidate(self._candidate(candidate_id="ethpc_two"))
        build_eth_paper_outcome(write=True, log_dir=self.log_dir)

        records = load_eth_paper_outcomes(limit=50, log_dir=self.log_dir)

        self.assertEqual(2, len(records))

    def test_outcome_summary_returns_btc_only_live_warning(self) -> None:
        summary = build_eth_paper_outcome_summary(log_dir=self.log_dir)

        self.assertEqual("ETHUSDT", summary["symbol"])
        self.assertEqual("ETHBTC", summary["rotation_pair"])
        self.assertIn("BTCUSDT remains the only live-readiness symbol", summary["warning"])
        self.assertFalse(summary["live_execution_enabled"])

    def test_api_eth_paper_outcome_works(self) -> None:
        response = self.client.get("/eth-paper/outcome")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("ETHUSDT", payload["symbol"])
        self.assertFalse(payload["order_placed"])

    def test_api_eth_paper_outcomes_works(self) -> None:
        self._append_candidate(self._candidate())
        build_eth_paper_outcome(write=True, log_dir=self.log_dir)

        response = self.client.get("/eth-paper/outcomes")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(1, len(payload["outcomes"]))
        self.assertFalse(payload["live_execution_enabled"])

    def test_api_eth_paper_outcome_summary_works(self) -> None:
        response = self.client.get("/eth-paper/outcome-summary")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("ETHUSDT", payload["symbol"])
        self.assertEqual("ETHBTC", payload["rotation_pair"])

    def test_cli_eth_paper_outcome_works(self) -> None:
        result = self._run_cli(["eth-paper-outcome"])

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("HAMMER RADAR ETHUSDT PAPER OUTCOME", result.stdout)

    def test_cli_eth_paper_outcomes_works(self) -> None:
        result = self._run_cli(["eth-paper-outcomes"])

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("HAMMER RADAR ETHUSDT PAPER OUTCOMES", result.stdout)

    def test_cli_eth_paper_outcome_summary_works(self) -> None:
        result = self._run_cli(["eth-paper-outcome-summary"])

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("HAMMER RADAR ETHUSDT PAPER OUTCOME SUMMARY", result.stdout)

    def test_ui_contains_eth_paper_outcome_panel(self) -> None:
        response = self.client.get("/ui")

        self.assertEqual(200, response.status_code)
        html = response.text
        self.assertIn("ETHUSDT Paper Outcome Tracker", html)
        self.assertIn("ETHUSDT outcomes are paper-only", html)
        self.assertIn("No ETH live tickets", html)

    def _append_candidate(self, record: dict) -> None:
        append_eth_candidate(record, log_dir=self.log_dir)

    def _candidate(
        self,
        *,
        candidate_id: str = "ethpc_test",
        direction: str = "long",
        last_price: float | None = 3200.0,
        paper_status: str = "PAPER_CANDIDATE",
        tier: str = "ETH_PAPER_CANDIDATE",
    ) -> dict:
        return {
            "candidate_id": candidate_id,
            "created_at": "2026-04-29T00:00:00+00:00",
            "source": "ethusdt_paper_candidate_engine",
            "symbol": "ETHUSDT",
            "rotation_pair": "ETHBTC",
            "ethbtc_rotation_state": "ETH_LEADING_BTC" if direction == "long" else "ETH_LAGGING_BTC",
            "ethbtc_change_percent_24h": 1.5 if direction == "long" else -1.5,
            "market_data_status": "OK",
            "direction": direction,
            "timeframe": "paper_context",
            "score": 100,
            "tier": tier,
            "paper_candidate_status": paper_status,
            "reason": "test candidate",
            "market_intelligence_score": 92,
            "momentum_score": 5,
            "liquidity_score": 10,
            "last_price": last_price,
            "price_change_percent_24h": 3.0 if direction == "long" else -3.0,
            "quote_volume_24h": 25000000.0,
            "suggested_position_usd": None,
            "suggested_leverage": 0,
            "live_eligible_symbol": False,
            "paper_watch_enabled": True,
            "watch_only": True,
            "live_execution_enabled": False,
            "order_placed": False,
        }

    def _run_cli(self, args: list[str]):
        return run(
            [".venv/bin/python", "-m", "src.app.hammer_radar.operator.inspect", "--log-dir", str(self.log_dir), *args],
            cwd=Path(__file__).resolve().parents[2],
            check=False,
            capture_output=True,
            text=True,
            env={LOG_DIR_ENV_VAR: str(self.log_dir), "PATH": os.environ.get("PATH", "")},
        )


if __name__ == "__main__":
    unittest.main()
