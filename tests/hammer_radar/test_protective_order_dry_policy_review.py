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

from src.app.hammer_radar.operator.protective_order_dry_policy_review import (
    CONFIRM_PROTECTIVE_REVIEW_PHRASE,
    EVENT_TYPE,
    LEDGER_FILENAME,
    PROTECTIVE_POLICY_BLOCKED,
    PROTECTIVE_POLICY_PREVIEW,
    PROTECTIVE_POLICY_READY_FOR_DRY_PAYLOAD_PREVIEW,
    PROTECTIVE_POLICY_REJECTED,
    append_protective_order_dry_policy_review_record,
    build_protective_order_dry_policy_review,
    load_protective_order_dry_policy_review_records,
)
from src.app.hammer_radar.operator.tiny_live_risk_contract import (
    DEFAULT_CANDIDATE_ID,
    build_tiny_live_risk_contract_payload,
)

LANE_KEY = "BTCUSDT|13m|long|ladder_close_50_618"


class ProtectiveOrderDryPolicyReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.log_dir = self.root / "logs"
        self.config_path = self.root / "lane_controls.json"
        self.now = datetime(2026, 5, 26, 14, 0, tzinfo=UTC)
        self._write_config("tiny_live")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_preview_writes_no_review_record(self) -> None:
        payload = self._review()

        self.assertEqual(PROTECTIVE_POLICY_PREVIEW, payload["status"])
        self.assertFalse(payload["review_recorded"])
        self.assertFalse((self.log_dir / LEDGER_FILENAME).exists())

    def test_wrong_confirmation_rejects_recording(self) -> None:
        payload = self._review(record_review=True, confirm_protective_review="wrong")

        self.assertEqual(PROTECTIVE_POLICY_REJECTED, payload["status"])
        self.assertFalse(payload["confirmation_valid"])
        self.assertFalse(payload["review_recorded"])
        self.assertFalse((self.log_dir / LEDGER_FILENAME).exists())

    def test_exact_confirmation_records_review_only_in_mocked_ready_state(self) -> None:
        payload = self._review(
            record_review=True,
            confirm_protective_review=CONFIRM_PROTECTIVE_REVIEW_PHRASE,
        )
        records = load_protective_order_dry_policy_review_records(log_dir=self.log_dir, limit=0)

        self.assertEqual(PROTECTIVE_POLICY_READY_FOR_DRY_PAYLOAD_PREVIEW, payload["status"])
        self.assertTrue(payload["review_recorded"])
        self.assertEqual(1, len(records))
        self.assertEqual(EVENT_TYPE, records[0]["event_type"])
        self.assertEqual(LANE_KEY, records[0]["lane_key"])
        self.assertEqual(payload["protective_policy_packet"]["protective_policy_hash"], records[0]["protective_policy_hash"])
        self.assertFalse(records[0]["safety"]["order_placed"])
        self.assertFalse(records[0]["safety"]["real_order_placed"])
        self.assertFalse(records[0]["safety"]["execution_attempted"])
        self.assertFalse(records[0]["safety"]["protective_payload_created"])
        self.assertFalse(records[0]["safety"]["signed_request_created"])
        self.assertFalse(records[0]["safety"]["protective_order_endpoint_called"])

    def test_protective_policy_packet_contains_no_secrets_or_executable_payload(self) -> None:
        payload = self._review(env={"BINANCE_API_KEY": "abc123", "BINANCE_API_SECRET": "supersecret"})
        packet = payload["protective_policy_packet"]
        rendered = json.dumps(packet).lower()

        self.assertNotIn("abc123", rendered)
        self.assertNotIn("supersecret", rendered)
        self.assertNotIn("api_key", rendered)
        self.assertNotIn("signature", rendered)
        self.assertNotIn("/fapi/v1/order", rendered)
        self.assertNotIn("recvwindow", rendered)
        self.assertNotIn("timestamp", rendered)
        self.assertIsNone(packet["stop_loss_policy"]["direct_exchange_payload"])
        self.assertIsNone(packet["take_profit_policy"]["direct_exchange_payload"])
        self.assertIsNone(packet["stop_loss_policy"]["signed_request"])
        self.assertIsNone(packet["take_profit_policy"]["signed_request"])

    def test_stop_and_take_profit_policy_are_non_executable(self) -> None:
        payload = self._review()
        areas = payload["policy_areas"]
        packet = payload["protective_policy_packet"]

        self.assertIsNone(packet["stop_loss_policy"]["direct_exchange_payload"])
        self.assertIsNone(packet["take_profit_policy"]["direct_exchange_payload"])
        self.assertIsNone(packet["stop_loss_policy"]["signed_request"])
        self.assertIsNone(packet["take_profit_policy"]["signed_request"])
        self.assertFalse(areas["stop_loss_policy_boundary"]["stop_executable_payload_created"])
        self.assertFalse(areas["take_profit_policy_boundary"]["take_profit_executable_payload_created"])
        self.assertFalse(payload["safety"]["protective_payload_created"])
        self.assertFalse(payload["safety"]["executable_payload_created"])
        self.assertFalse(payload["safety"]["binance_order_endpoint_called"])
        self.assertFalse(payload["safety"]["binance_test_order_endpoint_called"])
        self.assertFalse(payload["safety"]["protective_order_endpoint_called"])

    def test_blocked_when_protective_orders_disabled_or_preview_only(self) -> None:
        payload = self._review(
            protective_readiness={
                "protective_orders_required": True,
                "protective_orders_enabled": False,
                "protective_orders_ready": False,
                "protective_order_mode": "PREVIEW_ONLY",
                "blockers": ["protective orders disabled"],
            }
        )

        self.assertEqual(PROTECTIVE_POLICY_BLOCKED, payload["status"])
        self.assertIn("connector_protective_boundary: protective orders disabled", payload["main_blockers"])
        self.assertIn("connector_protective_boundary: protective orders are not ready", payload["main_blockers"])

    def test_blocked_when_stop_or_take_profit_references_missing(self) -> None:
        risk = build_tiny_live_risk_contract_payload(candidate_id=DEFAULT_CANDIDATE_ID)
        risk["risk_contract"].pop("stop_distance_pct", None)
        risk["risk_contract"].pop("take_profit_distance_pct", None)
        payload = self._review(risk_contract=risk, paper_records=[self._paper_proof(stop=None, take_profit=None)])

        self.assertEqual(PROTECTIVE_POLICY_BLOCKED, payload["status"])
        self.assertIn("stop_loss_policy_boundary: stop reference is missing", payload["main_blockers"])
        self.assertIn("take_profit_policy_boundary: take-profit reference is missing", payload["main_blockers"])

    def test_future_requirements_included(self) -> None:
        payload = self._review()

        self.assertGreaterEqual(len(payload["future_protective_payload_dry_preview_requirements"]), 5)
        self.assertTrue(any("R137" in item for item in payload["future_protective_payload_dry_preview_requirements"]))

    def test_safety_flags_are_always_false(self) -> None:
        payload = self._review()

        for key in (
            "order_placed",
            "real_order_placed",
            "execution_attempted",
            "order_payload_created",
            "executable_payload_created",
            "protective_payload_created",
            "signed_request_created",
            "network_allowed",
            "binance_order_endpoint_called",
            "binance_test_order_endpoint_called",
            "protective_order_endpoint_called",
            "secrets_shown",
            "env_mutated",
            "config_written",
            "global_live_flags_changed",
        ):
            self.assertFalse(payload["safety"][key])
        self.assertTrue(payload["safety"]["paper_live_separation_intact"])

    def test_ledger_append_only(self) -> None:
        first = self._review()
        second = self._review()
        append_protective_order_dry_policy_review_record(
            {
                "event_type": EVENT_TYPE,
                "review_id": "first",
                "recorded_at_utc": self.now.isoformat(),
                "status": PROTECTIVE_POLICY_READY_FOR_DRY_PAYLOAD_PREVIEW,
                "lane_key": LANE_KEY,
                "protective_policy_hash": first["protective_policy_packet"]["protective_policy_hash"],
                "protective_policy_packet": first["protective_policy_packet"],
                "safety": first["safety"],
            },
            log_dir=self.log_dir,
        )
        append_protective_order_dry_policy_review_record(
            {
                "event_type": EVENT_TYPE,
                "review_id": "second",
                "recorded_at_utc": self.now.isoformat(),
                "status": PROTECTIVE_POLICY_READY_FOR_DRY_PAYLOAD_PREVIEW,
                "lane_key": LANE_KEY,
                "protective_policy_hash": second["protective_policy_packet"]["protective_policy_hash"],
                "protective_policy_packet": second["protective_policy_packet"],
                "safety": second["safety"],
            },
            log_dir=self.log_dir,
        )
        records = load_protective_order_dry_policy_review_records(log_dir=self.log_dir, limit=0)

        self.assertEqual(2, len(records))
        self.assertEqual(["first", "second"], [record["review_id"] for record in records])

    def test_cli_mode_exists_and_returns_compact_status(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                str(self.log_dir),
                "protective-order-dry-policy-review",
                "--lane-key",
                LANE_KEY,
            ],
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": "."},
        )

        payload = json.loads(result.stdout)
        self.assertIn(payload["status"], {PROTECTIVE_POLICY_PREVIEW, PROTECTIVE_POLICY_BLOCKED})
        self.assertIn("protective_policy_packet", payload)
        self.assertIn("payload_forbidden_map", payload)
        self.assertIn("safety", payload)
        self.assertLess(len(result.stdout), 120000)

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
            payload = self._review(
                record_review=True,
                confirm_protective_review=CONFIRM_PROTECTIVE_REVIEW_PHRASE,
            )

        execute_live_order.assert_not_called()
        preview_payload.assert_not_called()
        protective_preview.assert_not_called()
        submit_test_order.assert_not_called()
        submit_protective_test.assert_not_called()
        build_signed_live_order_request.assert_not_called()
        build_signed_test_order_request.assert_not_called()
        build_signed_protective_order_requests.assert_not_called()
        self.assertEqual(PROTECTIVE_POLICY_READY_FOR_DRY_PAYLOAD_PREVIEW, payload["status"])

    def _review(self, **kwargs: object) -> dict[str, object]:
        return build_protective_order_dry_policy_review(
            log_dir=self.log_dir,
            lane_key=kwargs.pop("lane_key", LANE_KEY),
            config_path=self.config_path,
            env=kwargs.pop("env", {}),
            now=self.now,
            risk_contract=kwargs.pop("risk_contract", build_tiny_live_risk_contract_payload(candidate_id=DEFAULT_CANDIDATE_ID)),
            protective_readiness=kwargs.pop("protective_readiness", self._protective_ready()),
            connector_status=kwargs.pop("connector_status", self._connector_ready()),
            paper_records=kwargs.pop("paper_records", [self._paper_proof()]),
            integration_records=kwargs.pop("integration_records", []),
            r132_boundary_review=kwargs.pop("r132_boundary_review", self._r132_ready()),
            r134_dry_authorization=kwargs.pop("r134_dry_authorization", self._r134_ready()),
            r135_rehearsal=kwargs.pop("r135_rehearsal", self._r135_ready()),
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

    def _protective_ready(self) -> dict[str, object]:
        return {
            "protective_orders_required": True,
            "protective_orders_enabled": True,
            "protective_orders_ready": True,
            "protective_order_mode": "LIVE_PROTECTIVE_ENABLED",
            "protective_stop_supported": True,
            "protective_take_profit_supported": True,
            "blockers": [],
        }

    def _connector_ready(self) -> dict[str, object]:
        return {
            "connector_mode": "DRY_RUN_ONLY",
            "protective_order_mode": "LIVE_PROTECTIVE_ENABLED",
            "protective_orders_required": True,
            "protective_orders_ready": True,
            "blockers": [],
        }

    def _paper_proof(self, *, stop: float | None = 100.0, take_profit: float | None = 110.0) -> dict[str, object]:
        return {
            "event_type": "AUTONOMOUS_PAPER_LANE_EXECUTION",
            "paper_execution_id": "paper-proof",
            "recorded_at_utc": (self.now - timedelta(seconds=30)).isoformat(),
            "candidate_id": DEFAULT_CANDIDATE_ID,
            "lane_key": LANE_KEY,
            "paper_action": "PAPER_SHADOW_FOR_TINY_LIVE",
            "entry_reference": 105.0,
            "stop_reference": stop,
            "take_profit_reference": take_profit,
            "safety": self._safe(),
        }

    def _r132_ready(self) -> dict[str, object]:
        return {"status": "LIVE_ADAPTER_BOUNDARY_REVIEW_READY", "main_blockers": [], "safety": self._safe()}

    def _r134_ready(self) -> dict[str, object]:
        return {
            "status": "DRY_AUTHORIZATION_READY",
            "dry_authorization_packet": {
                "dry_authorization_hash": "r134-hash",
                "protective_intent": {"direct_exchange_payload": None, "signed_request": None},
            },
            "safety": self._safe(),
        }

    def _r135_ready(self) -> dict[str, object]:
        return {
            "status": "LIVE_ADAPTER_REHEARSAL_READY_FOR_FUTURE_IMPLEMENTATION",
            "rehearsal_areas": {"network_boundary": {"protective_order_endpoint_called": False}},
            "safety": self._safe(),
        }

    def _safe(self) -> dict[str, bool]:
        return {
            "order_placed": False,
            "real_order_placed": False,
            "execution_attempted": False,
            "order_payload_created": False,
            "executable_payload_created": False,
            "protective_payload_created": False,
            "signed_request_created": False,
            "network_allowed": False,
            "binance_order_endpoint_called": False,
            "binance_test_order_endpoint_called": False,
            "protective_order_endpoint_called": False,
            "secrets_shown": False,
            "paper_live_separation_intact": True,
            "env_mutated": False,
            "config_written": False,
            "global_live_flags_changed": False,
        }


if __name__ == "__main__":
    unittest.main()
