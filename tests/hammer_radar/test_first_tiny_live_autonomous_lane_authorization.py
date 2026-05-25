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
from src.app.hammer_radar.operator.first_tiny_live_autonomous_lane_authorization import (
    CONFIRM_TINY_LIVE_AUTHORIZATION_PHRASE,
    EVENT_TYPE,
    LEDGER_FILENAME,
    TINY_LIVE_AUTHORIZATION_BLOCKED,
    TINY_LIVE_AUTHORIZATION_PREVIEW,
    TINY_LIVE_AUTHORIZATION_RECORDED,
    TINY_LIVE_AUTHORIZATION_REJECTED,
    append_tiny_live_lane_authorization_record,
    build_first_tiny_live_autonomous_lane_authorization,
    load_tiny_live_lane_authorization_records,
)
from src.app.hammer_radar.operator.first_tiny_live_lane_execution_gate import TINY_LIVE_EXECUTION_BLOCKED, TINY_LIVE_EXECUTION_READY
from src.app.hammer_radar.operator.strategy_performance import ELIGIBLE_FOR_FUTURE_TINY_LIVE
from src.app.hammer_radar.operator.tiny_live_risk_contract import DEFAULT_CANDIDATE_ID, build_tiny_live_risk_contract_payload

LANE_KEY = "BTCUSDT|13m|long|ladder_close_50_618"


class FirstTinyLiveAutonomousLaneAuthorizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.log_dir = self.root / "logs"
        self.config_path = self.root / "lane_controls.json"
        self.now = datetime(2026, 5, 25, 17, 0, tzinfo=UTC)
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
                    "blockers": [],
                }
            ]
        }

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_preview_writes_no_authorization_record(self) -> None:
        payload = self._auth()

        self.assertEqual(TINY_LIVE_AUTHORIZATION_PREVIEW, payload["status"])
        self.assertFalse(payload["authorization_recorded"])
        self.assertFalse((self.log_dir / LEDGER_FILENAME).exists())

    def test_wrong_confirmation_rejects_recording(self) -> None:
        payload = self._auth(record_authorization=True, confirm_tiny_live_authorization="wrong")

        self.assertEqual(TINY_LIVE_AUTHORIZATION_REJECTED, payload["status"])
        self.assertFalse(payload["confirmation_valid"])
        self.assertFalse(payload["authorization_recorded"])
        self.assertFalse((self.log_dir / LEDGER_FILENAME).exists())

    def test_exact_confirmation_records_authorization_only_when_prerequisites_permit(self) -> None:
        payload = self._auth(
            record_authorization=True,
            confirm_tiny_live_authorization=CONFIRM_TINY_LIVE_AUTHORIZATION_PHRASE,
        )
        records = load_tiny_live_lane_authorization_records(log_dir=self.log_dir, limit=0)

        self.assertEqual(TINY_LIVE_AUTHORIZATION_RECORDED, payload["status"])
        self.assertTrue(payload["authorization_recorded"])
        self.assertEqual(1, len(records))
        self.assertEqual(EVENT_TYPE, records[0]["event_type"])
        self.assertEqual(LANE_KEY, records[0]["lane_key"])
        self.assertFalse(records[0]["safety"]["order_placed"])
        self.assertFalse(records[0]["safety"]["real_order_placed"])
        self.assertFalse(records[0]["safety"]["execution_attempted"])
        self.assertFalse(records[0]["safety"]["order_payload_created"])
        self.assertFalse(records[0]["safety"]["network_allowed"])
        self.assertFalse(records[0]["safety"]["secrets_shown"])

    def test_unknown_lane_rejected(self) -> None:
        payload = self._auth(lane_key="BTCUSDT|1m|long|ladder_close_50_618")

        self.assertEqual(TINY_LIVE_AUTHORIZATION_BLOCKED, payload["status"])
        self.assertIn("unknown lane_key", payload["blockers"])

    def test_missing_paper_proof_blocks_authorization(self) -> None:
        payload = self._auth(paper_records=[])

        self.assertEqual(TINY_LIVE_AUTHORIZATION_BLOCKED, payload["status"])
        self.assertIn("recent autonomous paper proof is missing", payload["blockers"])

    def test_r126_blocked_state_blocks_ready_authorization(self) -> None:
        payload = self._auth(r126_gate={"status": TINY_LIVE_EXECUTION_BLOCKED, "safety": self._safe()})

        self.assertEqual(TINY_LIVE_AUTHORIZATION_BLOCKED, payload["status"])
        self.assertIn(f"R126 tiny-live gate is not {TINY_LIVE_EXECUTION_READY}: {TINY_LIVE_EXECUTION_BLOCKED}", payload["blockers"])

    def test_authorization_packet_contains_no_secrets_or_executable_order_payload(self) -> None:
        payload = self._auth()
        rendered = json.dumps(payload["authorization_packet"]).lower()

        self.assertNotIn("secret", rendered)
        self.assertNotIn("api_key", rendered)
        self.assertNotIn("signature", rendered)
        self.assertNotIn("quantity", rendered)
        self.assertNotIn("/fapi/v1/order", rendered)
        self.assertNotIn("endpoint", rendered)
        self.assertIn("authorization_hash", payload["authorization_packet"])

    def test_safety_flags_are_false_and_separation_true(self) -> None:
        payload = self._auth()

        self.assertEqual(self._safe(), payload["safety"])

    def test_lane_mode_apply_is_blocked_and_recommends_r124(self) -> None:
        payload = self._auth(
            request_lane_mode_tiny_live=True,
            apply_lane_mode_change=True,
            confirm_tiny_live_authorization=CONFIRM_TINY_LIVE_AUTHORIZATION_PHRASE,
        )

        self.assertEqual(TINY_LIVE_AUTHORIZATION_BLOCKED, payload["status"])
        self.assertFalse(payload["config_written"])
        self.assertFalse(payload["lane_mode_change"]["config_written"])
        self.assertIn("use R124 lane-control-command for any actual lane mode mutation", payload["next_actions"])
        self.assertEqual("tiny_live", json.loads(self.config_path.read_text(encoding="utf-8"))["lanes"][0]["mode"])

    def test_lane_mode_apply_requires_confirmation_before_consideration(self) -> None:
        payload = self._auth(request_lane_mode_tiny_live=True, apply_lane_mode_change=True)

        self.assertEqual(TINY_LIVE_AUTHORIZATION_BLOCKED, payload["status"])
        self.assertIn(
            "exact tiny-live authorization confirmation phrase is required before lane mode apply can be considered",
            payload["blockers"],
        )
        self.assertFalse(payload["config_written"])

    def test_ledger_writes_append_only_authorization_records(self) -> None:
        first = self._auth(record_authorization=True, confirm_tiny_live_authorization=CONFIRM_TINY_LIVE_AUTHORIZATION_PHRASE)
        second = self._auth(record_authorization=True, confirm_tiny_live_authorization=CONFIRM_TINY_LIVE_AUTHORIZATION_PHRASE)
        records = load_tiny_live_lane_authorization_records(log_dir=self.log_dir, limit=0)

        self.assertEqual(TINY_LIVE_AUTHORIZATION_RECORDED, first["status"])
        self.assertEqual(TINY_LIVE_AUTHORIZATION_RECORDED, second["status"])
        self.assertEqual(2, len(records))
        self.assertEqual([first["authorization_id"], second["authorization_id"]], [row["authorization_id"] for row in records])

    def test_explicit_append_helper_is_append_only(self) -> None:
        base = {
            "event_type": EVENT_TYPE,
            "authorization_id": "manual",
            "recorded_at_utc": self.now.isoformat(),
            "lane_key": LANE_KEY,
            "authorization_status": TINY_LIVE_AUTHORIZATION_RECORDED,
            "safety": self._safe(),
        }
        append_tiny_live_lane_authorization_record(base, log_dir=self.log_dir)
        append_tiny_live_lane_authorization_record({**base, "authorization_id": "manual-2"}, log_dir=self.log_dir)

        self.assertEqual(2, len(load_tiny_live_lane_authorization_records(log_dir=self.log_dir, limit=0)))

    def test_cli_mode_exists_and_returns_compact_status(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                str(self.log_dir),
                "first-tiny-live-autonomous-lane-authorization",
                "--lane-key",
                LANE_KEY,
            ],
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": "."},
        )

        payload = json.loads(result.stdout)
        self.assertIn(payload["status"], {TINY_LIVE_AUTHORIZATION_PREVIEW, TINY_LIVE_AUTHORIZATION_BLOCKED})
        self.assertIn("authorization_packet", payload)
        self.assertIn("prerequisites", payload)
        self.assertLess(len(result.stdout), 20000)

    def test_no_binance_order_payload_or_network_calls_occur(self) -> None:
        from src.app.hammer_radar.execution import binance_futures_connector

        with (
            patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
            patch.object(binance_futures_connector, "preview_payload") as preview_payload,
            patch.object(binance_futures_connector, "protective_preview") as protective_preview,
            patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        ):
            payload = self._auth(record_authorization=True, confirm_tiny_live_authorization=CONFIRM_TINY_LIVE_AUTHORIZATION_PHRASE)

        execute_live_order.assert_not_called()
        preview_payload.assert_not_called()
        protective_preview.assert_not_called()
        submit_test_order.assert_not_called()
        self.assertFalse(payload["safety"]["order_payload_created"])
        self.assertFalse(payload["safety"]["network_allowed"])
        self.assertFalse(payload["safety"]["execution_attempted"])

    def _auth(self, **kwargs: object) -> dict[str, object]:
        return build_first_tiny_live_autonomous_lane_authorization(
            log_dir=self.log_dir,
            lane_key=kwargs.pop("lane_key", LANE_KEY),
            config_path=self.config_path,
            now=self.now,
            live_eligibility_matrix=self.matrix,
            r126_gate=kwargs.pop("r126_gate", {"status": TINY_LIVE_EXECUTION_READY, "readiness_packet": {"readiness_hash": "r126"}, "safety": self._safe()}),
            risk_contract=kwargs.pop("risk_contract", build_tiny_live_risk_contract_payload(candidate_id=DEFAULT_CANDIDATE_ID)),
            paper_records=kwargs.pop("paper_records", [self._paper_proof()]),
            integration_records=kwargs.pop("integration_records", []),
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

    def _paper_proof(self) -> dict[str, object]:
        return {
            "event_type": "AUTONOMOUS_PAPER_LANE_EXECUTION",
            "paper_execution_id": "paper-proof",
            "recorded_at_utc": (self.now - timedelta(minutes=1)).isoformat(),
            "candidate_id": DEFAULT_CANDIDATE_ID,
            "lane_key": LANE_KEY,
            "paper_action": PAPER_SHADOW_FOR_TINY_LIVE,
            "safety": self._safe(),
        }

    def _safe(self) -> dict[str, bool]:
        return {
            "order_placed": False,
            "real_order_placed": False,
            "execution_attempted": False,
            "order_payload_created": False,
            "network_allowed": False,
            "secrets_shown": False,
            "paper_live_separation_intact": True,
            "env_mutated": False,
            "global_live_flags_changed": False,
        }


if __name__ == "__main__":
    unittest.main()
