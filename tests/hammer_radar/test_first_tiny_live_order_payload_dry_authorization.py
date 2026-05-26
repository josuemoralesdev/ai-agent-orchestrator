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
from src.app.hammer_radar.operator.first_tiny_live_order_payload_dry_authorization import (
    CONFIRM_DRY_AUTHORIZATION_PHRASE,
    DRY_AUTHORIZATION_BLOCKED,
    DRY_AUTHORIZATION_PREVIEW,
    DRY_AUTHORIZATION_READY,
    DRY_AUTHORIZATION_REJECTED,
    EVENT_TYPE,
    LEDGER_FILENAME,
    append_dry_authorization_review_record,
    build_first_tiny_live_order_payload_dry_authorization,
    load_dry_authorization_review_records,
)
from src.app.hammer_radar.operator.first_tiny_live_autonomous_lane_authorization import (
    TINY_LIVE_AUTHORIZATION_BLOCKED,
    TINY_LIVE_AUTHORIZATION_RECORDED,
)
from src.app.hammer_radar.operator.first_tiny_live_lane_execution_gate import (
    TINY_LIVE_EXECUTION_BLOCKED,
    TINY_LIVE_EXECUTION_READY,
)
from src.app.hammer_radar.operator.live_adapter_boundary_final_review import (
    LIVE_ADAPTER_BOUNDARY_BLOCKED,
    LIVE_ADAPTER_BOUNDARY_REVIEW_READY,
)
from src.app.hammer_radar.operator.live_lane_kill_switch_rehearsal import KILL_SWITCH_REHEARSAL_READY
from src.app.hammer_radar.operator.tiny_live_risk_contract import (
    DEFAULT_CANDIDATE_ID,
    build_tiny_live_risk_contract_payload,
)

LANE_KEY = "BTCUSDT|13m|long|ladder_close_50_618"


class FirstTinyLiveOrderPayloadDryAuthorizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.log_dir = self.root / "logs"
        self.config_path = self.root / "lane_controls.json"
        self.now = datetime(2026, 5, 26, 12, 0, tzinfo=UTC)
        self._write_config("tiny_live")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_preview_writes_no_ledger_record(self) -> None:
        payload = self._auth()

        self.assertEqual(DRY_AUTHORIZATION_PREVIEW, payload["status"])
        self.assertFalse(payload["dry_authorization_recorded"])
        self.assertFalse((self.log_dir / LEDGER_FILENAME).exists())

    def test_wrong_confirmation_rejects_recording(self) -> None:
        payload = self._auth(record_dry_authorization=True, confirm_dry_authorization="wrong")

        self.assertEqual(DRY_AUTHORIZATION_REJECTED, payload["status"])
        self.assertFalse(payload["confirmation_valid"])
        self.assertFalse(payload["dry_authorization_recorded"])
        self.assertFalse((self.log_dir / LEDGER_FILENAME).exists())

    def test_exact_confirmation_records_dry_authorization_review_only_in_mocked_ready_state(self) -> None:
        payload = self._auth(
            record_dry_authorization=True,
            confirm_dry_authorization=CONFIRM_DRY_AUTHORIZATION_PHRASE,
        )
        records = load_dry_authorization_review_records(log_dir=self.log_dir, limit=0)

        self.assertEqual(DRY_AUTHORIZATION_READY, payload["status"])
        self.assertTrue(payload["dry_authorization_recorded"])
        self.assertEqual(1, len(records))
        self.assertEqual(EVENT_TYPE, records[0]["event_type"])
        self.assertEqual(LANE_KEY, records[0]["lane_key"])
        self.assertEqual(payload["dry_authorization_packet"]["dry_authorization_hash"], records[0]["dry_authorization_hash"])
        self.assertFalse(records[0]["safety"]["order_placed"])
        self.assertFalse(records[0]["safety"]["real_order_placed"])
        self.assertFalse(records[0]["safety"]["execution_attempted"])
        self.assertFalse(records[0]["safety"]["order_payload_created"])
        self.assertFalse(records[0]["safety"]["executable_payload_created"])
        self.assertFalse(records[0]["safety"]["signed_request_created"])
        self.assertFalse(records[0]["safety"]["network_allowed"])

    def test_blocked_when_lane_is_not_tiny_live(self) -> None:
        self._write_config("armed_dry_run")
        payload = self._auth()

        self.assertEqual(DRY_AUTHORIZATION_BLOCKED, payload["status"])
        self.assertIn("lane mode is not tiny_live: armed_dry_run", payload["blockers"])

    def test_blocked_when_r126_not_ready(self) -> None:
        payload = self._auth(r126_gate={**self._r126_ready(), "status": TINY_LIVE_EXECUTION_BLOCKED})

        self.assertEqual(DRY_AUTHORIZATION_BLOCKED, payload["status"])
        self.assertIn(f"R126 tiny-live execution gate is not {TINY_LIVE_EXECUTION_READY}: {TINY_LIVE_EXECUTION_BLOCKED}", payload["blockers"])

    def test_blocked_when_r130_missing_or_blocked(self) -> None:
        payload = self._auth(r130_authorization={**self._r130_ready(), "status": TINY_LIVE_AUTHORIZATION_BLOCKED, "authorization_recorded": False})

        self.assertEqual(DRY_AUTHORIZATION_BLOCKED, payload["status"])
        self.assertIn("R130 tiny-live authorization is missing or blocked", payload["blockers"])

    def test_blocked_when_r132_missing_or_blocked(self) -> None:
        payload = self._auth(r132_boundary_review={**self._r132_ready(), "status": LIVE_ADAPTER_BOUNDARY_BLOCKED})

        self.assertEqual(DRY_AUTHORIZATION_BLOCKED, payload["status"])
        self.assertIn("R132 live adapter boundary review is not ready and clear", payload["blockers"])

    def test_blocked_when_recent_paper_proof_missing(self) -> None:
        payload = self._auth(paper_records=[], integration_records=[])

        self.assertEqual(DRY_AUTHORIZATION_BLOCKED, payload["status"])
        self.assertIn("recent autonomous paper proof is missing", payload["blockers"])

    def test_dry_authorization_packet_contains_no_secrets_or_executable_payload(self) -> None:
        payload = self._auth()
        packet = payload["dry_authorization_packet"]
        rendered = json.dumps(packet).lower()

        self.assertNotIn("secret", rendered)
        self.assertNotIn("api_key", rendered)
        self.assertNotIn("signature", rendered)
        self.assertNotIn("/fapi/v1/order", rendered)
        self.assertNotIn("recvwindow", rendered)
        self.assertNotIn("timestamp", rendered)
        self.assertIsNone(packet["entry_intent"]["direct_exchange_payload"])
        self.assertIsNone(packet["protective_intent"]["direct_exchange_payload"])
        self.assertIsNone(packet["entry_intent"]["signed_request"])
        self.assertIsNone(packet["protective_intent"]["signed_request"])
        self.assertIsNone(packet["size_policy"]["direct_live_quantity"])

    def test_safety_flags_are_always_false(self) -> None:
        payload = self._auth()

        for key in (
            "order_placed",
            "real_order_placed",
            "execution_attempted",
            "order_payload_created",
            "executable_payload_created",
            "signed_request_created",
            "network_allowed",
            "binance_order_endpoint_called",
            "binance_test_order_endpoint_called",
            "secrets_shown",
            "env_mutated",
            "config_written",
            "global_live_flags_changed",
        ):
            self.assertFalse(payload["safety"][key])
        self.assertTrue(payload["safety"]["paper_live_separation_intact"])

    def test_ledger_append_only(self) -> None:
        first = self._auth()
        second = self._auth()
        append_dry_authorization_review_record(
            {
                "event_type": EVENT_TYPE,
                "dry_authorization_id": "first",
                "recorded_at_utc": self.now.isoformat(),
                "status": DRY_AUTHORIZATION_READY,
                "lane_key": LANE_KEY,
                "dry_authorization_hash": first["dry_authorization_packet"]["dry_authorization_hash"],
                "dry_authorization_packet": first["dry_authorization_packet"],
                "safety": first["safety"],
            },
            log_dir=self.log_dir,
        )
        append_dry_authorization_review_record(
            {
                "event_type": EVENT_TYPE,
                "dry_authorization_id": "second",
                "recorded_at_utc": self.now.isoformat(),
                "status": DRY_AUTHORIZATION_READY,
                "lane_key": LANE_KEY,
                "dry_authorization_hash": second["dry_authorization_packet"]["dry_authorization_hash"],
                "dry_authorization_packet": second["dry_authorization_packet"],
                "safety": second["safety"],
            },
            log_dir=self.log_dir,
        )
        records = load_dry_authorization_review_records(log_dir=self.log_dir, limit=0)

        self.assertEqual(2, len(records))
        self.assertEqual(["first", "second"], [record["dry_authorization_id"] for record in records])

    def test_cli_mode_exists_and_returns_compact_status(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                str(self.log_dir),
                "first-tiny-live-order-payload-dry-authorization",
                "--lane-key",
                LANE_KEY,
            ],
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": "."},
        )

        payload = json.loads(result.stdout)
        self.assertIn(payload["status"], {DRY_AUTHORIZATION_PREVIEW, DRY_AUTHORIZATION_BLOCKED})
        self.assertIn("dry_authorization_packet", payload)
        self.assertIn("safety", payload)
        self.assertLess(len(result.stdout), 50000)

    def test_no_binance_order_payload_network_or_signed_calls_occur(self) -> None:
        from src.app.hammer_radar.execution import binance_futures_connector

        with (
            patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
            patch.object(binance_futures_connector, "preview_payload") as preview_payload,
            patch.object(binance_futures_connector, "protective_preview") as protective_preview,
            patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
            patch.object(binance_futures_connector, "submit_protective_test") as submit_protective_test,
            patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
            patch.object(binance_futures_connector, "build_signed_test_order_request") as build_signed_test_order_request,
            patch.object(binance_futures_connector, "build_signed_protective_order_requests") as build_signed_protective_order_requests,
        ):
            payload = self._auth(
                record_dry_authorization=True,
                confirm_dry_authorization=CONFIRM_DRY_AUTHORIZATION_PHRASE,
            )

        execute_live_order.assert_not_called()
        preview_payload.assert_not_called()
        protective_preview.assert_not_called()
        submit_test_order.assert_not_called()
        submit_protective_test.assert_not_called()
        build_signed_live_order_request.assert_not_called()
        build_signed_test_order_request.assert_not_called()
        build_signed_protective_order_requests.assert_not_called()
        self.assertEqual(DRY_AUTHORIZATION_READY, payload["status"])
        self.assertFalse(payload["safety"]["binance_order_endpoint_called"])
        self.assertFalse(payload["safety"]["binance_test_order_endpoint_called"])

    def _auth(self, **kwargs: object) -> dict[str, object]:
        return build_first_tiny_live_order_payload_dry_authorization(
            log_dir=self.log_dir,
            lane_key=kwargs.pop("lane_key", LANE_KEY),
            config_path=self.config_path,
            env=kwargs.pop("env", {"BINANCE_API_KEY": "present", "BINANCE_API_SECRET": "present"}),
            now=self.now,
            r126_gate=kwargs.pop("r126_gate", self._r126_ready()),
            r130_authorization=kwargs.pop("r130_authorization", self._r130_ready()),
            r131_rehearsal=kwargs.pop("r131_rehearsal", self._r131_ready()),
            r132_boundary_review=kwargs.pop("r132_boundary_review", self._r132_ready()),
            r106_gate=kwargs.pop("r106_gate", {"status": "FIRST_LIVE_ACTIVATION_READY"}),
            risk_contract=kwargs.pop("risk_contract", build_tiny_live_risk_contract_payload(candidate_id=DEFAULT_CANDIDATE_ID)),
            protective_readiness=kwargs.pop("protective_readiness", {"protective_orders_ready": True, "protective_order_mode": "LIVE_PROTECTIVE_ENABLED", "blockers": []}),
            paper_records=kwargs.pop("paper_records", [self._paper_proof()]),
            integration_records=kwargs.pop("integration_records", []),
            authorization_records=kwargs.pop("authorization_records", []),
            boundary_review_records=kwargs.pop("boundary_review_records", []),
            **kwargs,
        )

    def _write_config(self, mode: str) -> None:
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

    def _r126_ready(self) -> dict[str, object]:
        return {
            "status": TINY_LIVE_EXECUTION_READY,
            "readiness_packet": {
                "candidate_id": DEFAULT_CANDIDATE_ID,
                "lane_key": LANE_KEY,
                "readiness_hash": "r126-hash",
            },
            "r106_gate": {"status": "FIRST_LIVE_ACTIVATION_READY"},
            "safety": self._safe(),
            "blockers": [],
        }

    def _r130_ready(self) -> dict[str, object]:
        return {
            "status": TINY_LIVE_AUTHORIZATION_RECORDED,
            "authorization_recorded": True,
            "authorization_id": "r130-auth",
            "authorization_packet": {"authorization_hash": "r130-hash"},
            "safety": self._safe(),
            "blockers": [],
        }

    def _r131_ready(self) -> dict[str, object]:
        return {
            "status": KILL_SWITCH_REHEARSAL_READY,
            "safety": self._safe(),
            "current_blockers": [],
            "kill_switch_verdict": {
                "global_kill_switch_blocks_live_intent": True,
                "lane_disable_blocks_live_intent": True,
                "rollback_blocks_live_intent": True,
                "scheduler_respects_disabled_lane": True,
            },
        }

    def _r132_ready(self) -> dict[str, object]:
        return {
            "status": LIVE_ADAPTER_BOUNDARY_REVIEW_READY,
            "review_id": "r132-review",
            "main_blockers": [],
            "boundary_reviews": {"dry_authorization_readiness": {"review_completed": True, "blockers": []}},
            "safety": self._safe(),
        }

    def _paper_proof(self) -> dict[str, object]:
        return {
            "event_type": "AUTONOMOUS_PAPER_LANE_EXECUTION",
            "paper_execution_id": "paper-proof",
            "recorded_at_utc": (self.now - timedelta(seconds=30)).isoformat(),
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
            "executable_payload_created": False,
            "signed_request_created": False,
            "network_allowed": False,
            "binance_order_endpoint_called": False,
            "binance_test_order_endpoint_called": False,
            "secrets_shown": False,
            "paper_live_separation_intact": True,
            "env_mutated": False,
            "config_written": False,
            "global_live_flags_changed": False,
        }


if __name__ == "__main__":
    unittest.main()
