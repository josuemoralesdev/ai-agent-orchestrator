from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.autonomous_paper_lane_execution import PAPER_SHADOW_FOR_TINY_LIVE
from src.app.hammer_radar.operator.first_tiny_live_lane_execution_gate import (
    EVENT_TYPE,
    REQUIRED_CONFIRMATION_PHRASE,
    TINY_LIVE_EXECUTION_BLOCKED,
    TINY_LIVE_EXECUTION_READY,
    append_tiny_live_gate_review_record,
    build_first_tiny_live_lane_execution_gate,
    tiny_live_gate_review_records_path,
)
from src.app.hammer_radar.operator.strategy_performance import ELIGIBLE_FOR_FUTURE_TINY_LIVE
from src.app.hammer_radar.operator.tiny_live_risk_contract import DEFAULT_CANDIDATE_ID, build_tiny_live_risk_contract_payload


LANE_KEY = "BTCUSDT|13m|long|ladder_close_50_618"


class FirstTinyLiveLaneExecutionGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.log_dir = self.root / "logs"
        self.config_path = self.root / "lane_controls.json"
        self.now = datetime(2026, 5, 25, 15, 0, tzinfo=UTC)
        self._write_config(mode="tiny_live")
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
                }
            ]
        }

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_returns_blocked_when_no_fresh_candidate(self) -> None:
        payload = self._gate(candidates=[])

        self.assertEqual(TINY_LIVE_EXECUTION_BLOCKED, payload["status"])
        self.assertIn("no fresh routed candidate", payload["blockers"])
        self.assertTrue(payload["safety"]["paper_live_separation_intact"])

    def test_returns_blocked_when_lane_mode_is_not_tiny_live(self) -> None:
        self._write_config(mode="paper")
        payload = self._gate(candidates=[self._candidate()])

        self.assertEqual(TINY_LIVE_EXECUTION_BLOCKED, payload["status"])
        self.assertIn("lane mode is not tiny_live: paper", payload["blockers"])

    def test_returns_blocked_when_r106_is_blocked(self) -> None:
        payload = self._gate(
            candidates=[self._candidate()],
            r106_gate={"status": "FIRST_LIVE_BLOCKED", "execution_enabled_by_gate": False},
        )

        self.assertEqual(TINY_LIVE_EXECUTION_BLOCKED, payload["status"])
        self.assertIn("R106 first-live activation gate is not FIRST_LIVE_ACTIVATION_READY", payload["blockers"])

    def test_returns_blocked_when_paper_proof_missing(self) -> None:
        payload = self._gate(candidates=[self._candidate()])

        self.assertEqual(TINY_LIVE_EXECUTION_BLOCKED, payload["status"])
        self.assertIn("no recent R125 paper execution or paper shadow for same lane/candidate tuple", payload["blockers"])

    def test_returns_blocked_when_protective_readiness_false(self) -> None:
        payload = self._gate(
            candidates=[self._candidate()],
            paper_records=[self._paper_proof()],
            protective_readiness={"protective_orders_ready": False, "blockers": ["protective missing"]},
        )

        self.assertEqual(TINY_LIVE_EXECUTION_BLOCKED, payload["status"])
        self.assertIn("protective order readiness is false", payload["blockers"])

    def test_returns_blocked_when_confirmation_missing(self) -> None:
        payload = self._gate(candidates=[self._candidate()], paper_records=[self._paper_proof()])

        self.assertEqual(TINY_LIVE_EXECUTION_BLOCKED, payload["status"])
        self.assertIn("operator confirmation phrase missing or invalid", payload["blockers"])

    def test_can_return_ready_only_in_fully_mocked_safe_ready_state(self) -> None:
        payload = self._gate(
            candidates=[self._candidate()],
            paper_records=[self._paper_proof()],
            confirm_review_only=REQUIRED_CONFIRMATION_PHRASE,
        )

        self.assertEqual(TINY_LIVE_EXECUTION_READY, payload["status"])
        self.assertEqual([], payload["blockers"])
        self.assertTrue(payload["operator_confirmation"]["valid"])
        self.assertEqual(DEFAULT_CANDIDATE_ID, payload["readiness_packet"]["candidate_id"])
        self.assertEqual(LANE_KEY, payload["readiness_packet"]["lane_key"])

    def test_readiness_packet_contains_no_secrets_or_executable_order_payload(self) -> None:
        payload = self._gate(
            candidates=[self._candidate()],
            paper_records=[self._paper_proof()],
            confirm_review_only=REQUIRED_CONFIRMATION_PHRASE,
        )
        rendered = json.dumps(payload["readiness_packet"]).lower()

        self.assertNotIn("secret", rendered)
        self.assertNotIn("api_key", rendered)
        self.assertNotIn("signature", rendered)
        self.assertNotIn("quantity", rendered)
        self.assertNotIn("/fapi/v1/order", rendered)
        self.assertNotIn("endpoint", rendered)
        self.assertIn("readiness_hash", payload["readiness_packet"])

    def test_safety_flags_always_false_and_separation_true(self) -> None:
        payload = self._gate(candidates=[self._candidate()])

        self.assertEqual(
            {
                "order_placed": False,
                "real_order_placed": False,
                "execution_attempted": False,
                "order_payload_created": False,
                "network_allowed": False,
                "secrets_shown": False,
                "paper_live_separation_intact": True,
            },
            payload["safety"],
        )

    def test_ledger_writes_append_only_gate_review_records(self) -> None:
        first = self._gate(candidates=[], record=False)
        second = self._gate(candidates=[], record=False)
        append_tiny_live_gate_review_record(first, log_dir=self.log_dir)
        append_tiny_live_gate_review_record(second, log_dir=self.log_dir)
        records = [
            json.loads(line)
            for line in tiny_live_gate_review_records_path(self.log_dir).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

        self.assertEqual(2, len(records))
        for record in records:
            self.assertEqual(EVENT_TYPE, record["event_type"])
            self.assertEqual(TINY_LIVE_EXECUTION_BLOCKED, record["status"])
            self.assertFalse(record["order_placed"])
            self.assertFalse(record["real_order_placed"])
            self.assertFalse(record["execution_attempted"])
            self.assertFalse(record["order_payload_created"])
            self.assertFalse(record["network_allowed"])
            self.assertFalse(record["secrets_shown"])
            self.assertTrue(record["paper_live_separation_intact"])

    def test_cli_mode_exists_and_returns_compact_status(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                str(self.log_dir),
                "first-tiny-live-lane-execution-gate",
            ],
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": "."},
        )

        payload = json.loads(result.stdout)
        self.assertEqual(TINY_LIVE_EXECUTION_BLOCKED, payload["status"])
        self.assertIn("readiness_packet", payload)
        self.assertIn("source_surfaces_used", payload)
        self.assertNotIn("routed_candidates", payload)
        self.assertNotIn("recommendations", result.stdout)
        self.assertLess(len(result.stdout), 10000)

    def test_no_binance_order_payload_or_network_calls_occur(self) -> None:
        from src.app.hammer_radar.execution import binance_futures_connector

        with (
            patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
            patch.object(binance_futures_connector, "preview_payload") as preview_payload,
            patch.object(binance_futures_connector, "protective_preview") as protective_preview,
            patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        ):
            payload = self._gate(candidates=[self._candidate()])

        execute_live_order.assert_not_called()
        preview_payload.assert_not_called()
        protective_preview.assert_not_called()
        submit_test_order.assert_not_called()
        self.assertFalse(payload["safety"]["order_payload_created"])
        self.assertFalse(payload["safety"]["network_allowed"])
        self.assertFalse(payload["safety"]["execution_attempted"])

    def _gate(self, **kwargs: object) -> dict[str, object]:
        return build_first_tiny_live_lane_execution_gate(
            log_dir=self.log_dir,
            config_path=self.config_path,
            now=self.now,
            live_eligibility_matrix=self.matrix,
            r106_gate=kwargs.pop("r106_gate", self._r106_ready()),
            global_gates=kwargs.pop("global_gates", self._global_ready()),
            risk_contract=kwargs.pop("risk_contract", build_tiny_live_risk_contract_payload(candidate_id=DEFAULT_CANDIDATE_ID)),
            protective_readiness=kwargs.pop("protective_readiness", {"protective_orders_ready": True, "protective_order_mode": "LIVE_PROTECTIVE_ENABLED"}),
            env={},
            **kwargs,
        )

    def _write_config(self, *, mode: str) -> None:
        self.config_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "default_mode": "disabled",
                    "notes": ["test"],
                    "lanes": [
                        {
                            "symbol": "BTCUSDT",
                            "timeframe": "13m",
                            "direction": "long",
                            "entry_mode": "ladder_close_50_618",
                            "mode": mode,
                            "max_daily_trades": 1,
                            "max_daily_loss_pct": 0.25,
                            "freshness_seconds": 120,
                            "cooldown_after_loss_minutes": 120,
                            "require_protective_orders": True,
                        }
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def _candidate(self) -> dict[str, object]:
        return {
            "candidate_id": DEFAULT_CANDIDATE_ID,
            "symbol": "BTCUSDT",
            "timeframe": "13m",
            "direction": "long",
            "entry_mode": "ladder_close_50_618",
            "generated_at": (self.now - timedelta(seconds=30)).isoformat(),
            "score": 101,
        }

    def _paper_proof(self) -> dict[str, object]:
        return {
            "event_type": "AUTONOMOUS_PAPER_LANE_EXECUTION",
            "paper_execution_id": "paper-proof-1",
            "recorded_at_utc": (self.now - timedelta(seconds=10)).isoformat(),
            "candidate_id": DEFAULT_CANDIDATE_ID,
            "lane_key": LANE_KEY,
            "paper_action": PAPER_SHADOW_FOR_TINY_LIVE,
            "safety": {
                "order_placed": False,
                "real_order_placed": False,
                "execution_attempted": False,
                "order_payload_created": False,
                "network_allowed": False,
                "secrets_shown": False,
                "paper_live_separation_intact": True,
            },
        }

    @staticmethod
    def _r106_ready() -> dict[str, object]:
        return {
            "status": "FIRST_LIVE_ACTIVATION_READY",
            "execution_enabled_by_gate": True,
            "candidate_id": DEFAULT_CANDIDATE_ID,
            "blockers": [],
            "warnings": [],
            "source_surfaces_used": ["test.r106"],
        }

    @staticmethod
    def _global_ready() -> dict[str, object]:
        return {
            "status": "READY",
            "live_execution_enabled": True,
            "live_orders_allowed": True,
            "global_kill_switch": False,
            "connector_mode": "LIVE_ORDER_ENABLED",
            "binance_credentials_present": {"api_key_present": True, "api_secret_present": True},
            "binance_account_status": {"account_balance_checked": False, "status": "read_only_present"},
            "protective_orders_ready": True,
            "no_conflicting_position_known": True,
            "emergency_cancel_reviewed": True,
            "paper_live_separation_intact": True,
            "blockers": [],
            "source_surfaces_used": ["test.global_gates"],
        }


if __name__ == "__main__":
    unittest.main()
