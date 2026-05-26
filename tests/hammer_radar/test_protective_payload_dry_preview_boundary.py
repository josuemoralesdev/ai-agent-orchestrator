from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.protective_order_dry_policy_review import (
    PROTECTIVE_POLICY_BLOCKED,
    PROTECTIVE_POLICY_READY_FOR_DRY_PAYLOAD_PREVIEW,
)
from src.app.hammer_radar.operator.protective_payload_dry_preview_boundary import (
    CONFIRM_PROTECTIVE_PREVIEW_PHRASE,
    EVENT_TYPE,
    LEDGER_FILENAME,
    PROTECTIVE_PAYLOAD_BLOCKED,
    PROTECTIVE_PAYLOAD_PREVIEW,
    PROTECTIVE_PAYLOAD_READY_FOR_FUTURE_DRY_RUN,
    PROTECTIVE_PAYLOAD_REJECTED,
    append_protective_payload_dry_preview_record,
    build_protective_payload_dry_preview_boundary,
    load_protective_payload_dry_preview_records,
)

LANE_KEY = "BTCUSDT|13m|long|ladder_close_50_618"


class ProtectivePayloadDryPreviewBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.log_dir = self.root / "logs"
        self.config_path = self.root / "lane_controls.json"
        self.now = datetime(2026, 5, 26, 15, 0, tzinfo=UTC)
        self._write_config("tiny_live")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_preview_writes_no_review_record(self) -> None:
        payload = self._preview()

        self.assertEqual(PROTECTIVE_PAYLOAD_PREVIEW, payload["status"])
        self.assertFalse(payload["preview_recorded"])
        self.assertFalse((self.log_dir / LEDGER_FILENAME).exists())

    def test_wrong_confirmation_rejects_recording(self) -> None:
        payload = self._preview(record_preview=True, confirm_protective_preview="wrong")

        self.assertEqual(PROTECTIVE_PAYLOAD_REJECTED, payload["status"])
        self.assertFalse(payload["confirmation_valid"])
        self.assertFalse(payload["preview_recorded"])
        self.assertFalse((self.log_dir / LEDGER_FILENAME).exists())

    def test_exact_confirmation_records_preview_only_in_mocked_ready_safe_state(self) -> None:
        payload = self._preview(
            record_preview=True,
            confirm_protective_preview=CONFIRM_PROTECTIVE_PREVIEW_PHRASE,
        )
        records = load_protective_payload_dry_preview_records(log_dir=self.log_dir, limit=0)

        self.assertEqual(PROTECTIVE_PAYLOAD_READY_FOR_FUTURE_DRY_RUN, payload["status"])
        self.assertTrue(payload["preview_recorded"])
        self.assertEqual(1, len(records))
        self.assertEqual(EVENT_TYPE, records[0]["event_type"])
        self.assertEqual(LANE_KEY, records[0]["lane_key"])
        self.assertEqual(payload["protective_preview_packet"]["protective_preview_hash"], records[0]["protective_preview_hash"])
        self.assertFalse(records[0]["safety"]["protective_payload_created"])
        self.assertFalse(records[0]["safety"]["executable_payload_created"])
        self.assertFalse(records[0]["safety"]["signed_request_created"])
        self.assertFalse(records[0]["safety"]["protective_order_endpoint_called"])

    def test_protective_preview_packet_contains_no_secrets(self) -> None:
        payload = self._preview(env={"BINANCE_API_KEY": "abc123", "BINANCE_API_SECRET": "supersecret"})
        rendered = json.dumps(payload["protective_preview_packet"]).lower()

        self.assertNotIn("abc123", rendered)
        self.assertNotIn("supersecret", rendered)
        self.assertNotIn("api_key", rendered)
        self.assertNotIn("api_secret", rendered)
        self.assertNotIn("x-mbx-apikey", rendered)

    def test_protective_preview_packet_contains_no_executable_exchange_payload(self) -> None:
        packet = self._preview()["protective_preview_packet"]
        rendered = json.dumps(packet).lower()

        self.assertNotIn("/fapi/v1/order", rendered)
        self.assertNotIn("recvwindow", rendered)
        self.assertNotIn("timestamp", rendered)
        self.assertNotIn("query_string", rendered)
        self.assertNotIn("base_url", rendered)
        self.assertIsNone(packet["risk_validation"]["direct_live_quantity"])

    def test_stop_loss_preview_is_null_for_executable_fields(self) -> None:
        stop = self._preview()["protective_preview_packet"]["stop_loss_preview"]

        self.assertIsNone(stop["direct_exchange_payload"])
        self.assertIsNone(stop["signed_request"])
        self.assertIsNone(stop["endpoint"])
        self.assertIsNone(stop["quantity"])

    def test_take_profit_preview_is_null_for_executable_fields(self) -> None:
        take = self._preview()["protective_preview_packet"]["take_profit_preview"]

        self.assertIsNone(take["direct_exchange_payload"])
        self.assertIsNone(take["signed_request"])
        self.assertIsNone(take["endpoint"])
        self.assertIsNone(take["quantity"])

    def test_forbidden_fields_present_is_empty_in_safe_preview(self) -> None:
        payload = self._preview()

        self.assertEqual([], payload["protective_preview_packet"]["forbidden_fields_present"])
        self.assertEqual([], payload["forbidden_field_report"]["forbidden_fields_present"])

    def test_safety_flags_are_always_false(self) -> None:
        payload = self._preview()

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

    def test_blocked_when_r136_policy_missing_or_blocked(self) -> None:
        payload = self._preview(r136_policy_review=self._r136_review(status=PROTECTIVE_POLICY_BLOCKED), r136_policy_records=[])

        self.assertEqual(PROTECTIVE_PAYLOAD_BLOCKED, payload["status"])
        self.assertIn("policy_source_boundary: R136 ready policy review record is missing", payload["main_blockers"])
        self.assertTrue(any("R136 policy review is not" in blocker for blocker in payload["main_blockers"]))

    def test_blocked_when_stop_take_profit_references_missing(self) -> None:
        payload = self._preview(r136_policy_review=self._r136_review(stop=None, take_profit=None), r136_policy_records=[self._r136_record(stop=None, take_profit=None)])

        self.assertEqual(PROTECTIVE_PAYLOAD_BLOCKED, payload["status"])
        self.assertIn("policy_source_boundary: stop policy reference is missing", payload["main_blockers"])
        self.assertIn("policy_source_boundary: take-profit policy reference is missing", payload["main_blockers"])

    def test_future_requirements_included(self) -> None:
        payload = self._preview()

        self.assertGreaterEqual(len(payload["future_protective_payload_requirements"]), 5)
        self.assertTrue(any("R138" in item or "R139" in item for item in payload["future_protective_payload_requirements"]))

    def test_ledger_append_only(self) -> None:
        first = self._preview()
        second = self._preview()
        append_protective_payload_dry_preview_record(
            {
                "event_type": EVENT_TYPE,
                "preview_id": "first",
                "recorded_at_utc": self.now.isoformat(),
                "status": PROTECTIVE_PAYLOAD_READY_FOR_FUTURE_DRY_RUN,
                "lane_key": LANE_KEY,
                "protective_preview_hash": first["protective_preview_packet"]["protective_preview_hash"],
                "protective_preview_packet": first["protective_preview_packet"],
                "safety": first["safety"],
            },
            log_dir=self.log_dir,
        )
        append_protective_payload_dry_preview_record(
            {
                "event_type": EVENT_TYPE,
                "preview_id": "second",
                "recorded_at_utc": self.now.isoformat(),
                "status": PROTECTIVE_PAYLOAD_READY_FOR_FUTURE_DRY_RUN,
                "lane_key": LANE_KEY,
                "protective_preview_hash": second["protective_preview_packet"]["protective_preview_hash"],
                "protective_preview_packet": second["protective_preview_packet"],
                "safety": second["safety"],
            },
            log_dir=self.log_dir,
        )
        records = load_protective_payload_dry_preview_records(log_dir=self.log_dir, limit=0)

        self.assertEqual(2, len(records))
        self.assertEqual(["first", "second"], [record["preview_id"] for record in records])

    def test_cli_mode_exists_and_returns_compact_status(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                str(self.log_dir),
                "protective-payload-dry-preview-boundary",
                "--lane-key",
                LANE_KEY,
            ],
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": "."},
        )

        payload = json.loads(result.stdout)
        self.assertIn(payload["status"], {PROTECTIVE_PAYLOAD_PREVIEW, PROTECTIVE_PAYLOAD_BLOCKED})
        self.assertIn("protective_preview_packet", payload)
        self.assertIn("forbidden_field_report", payload)
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
            payload = self._preview(
                record_preview=True,
                confirm_protective_preview=CONFIRM_PROTECTIVE_PREVIEW_PHRASE,
            )

        execute_live_order.assert_not_called()
        preview_payload.assert_not_called()
        protective_preview.assert_not_called()
        submit_test_order.assert_not_called()
        submit_protective_test.assert_not_called()
        build_signed_live_order_request.assert_not_called()
        build_signed_test_order_request.assert_not_called()
        build_signed_protective_order_requests.assert_not_called()
        self.assertEqual(PROTECTIVE_PAYLOAD_READY_FOR_FUTURE_DRY_RUN, payload["status"])
        self.assertFalse(payload["safety"]["binance_order_endpoint_called"])
        self.assertFalse(payload["safety"]["binance_test_order_endpoint_called"])
        self.assertFalse(payload["safety"]["protective_order_endpoint_called"])

    def _preview(self, **kwargs: object) -> dict[str, object]:
        kwargs.setdefault("r136_policy_review", self._r136_review())
        kwargs.setdefault("r136_policy_records", [self._r136_record()])
        kwargs.setdefault("connector_status", self._connector_status())
        kwargs.setdefault("protective_status", self._protective_status())
        return build_protective_payload_dry_preview_boundary(
            log_dir=self.log_dir,
            lane_key=kwargs.pop("lane_key", LANE_KEY),
            config_path=self.config_path,
            env=kwargs.pop("env", {}),
            now=self.now,
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

    def _r136_review(
        self,
        *,
        status: str = PROTECTIVE_POLICY_READY_FOR_DRY_PAYLOAD_PREVIEW,
        stop: float | None = 100.0,
        take_profit: float | None = 110.0,
    ) -> dict[str, object]:
        return {
            "status": status,
            "lane_key": LANE_KEY,
            "protective_policy_packet": self._policy_packet(stop=stop, take_profit=take_profit),
            "main_blockers": [] if status == PROTECTIVE_POLICY_READY_FOR_DRY_PAYLOAD_PREVIEW else ["blocked"],
            "safety": self._safe(),
        }

    def _r136_record(
        self,
        *,
        status: str = PROTECTIVE_POLICY_READY_FOR_DRY_PAYLOAD_PREVIEW,
        stop: float | None = 100.0,
        take_profit: float | None = 110.0,
    ) -> dict[str, object]:
        packet = self._policy_packet(stop=stop, take_profit=take_profit)
        return {
            "event_type": "PROTECTIVE_ORDER_DRY_POLICY_REVIEW",
            "review_id": "r136-ready",
            "recorded_at_utc": self.now.isoformat(),
            "status": status,
            "lane_key": LANE_KEY,
            "protective_policy_hash": packet["protective_policy_hash"],
            "protective_policy_packet": packet,
            "safety": self._safe(),
        }

    def _policy_packet(self, *, stop: float | None = 100.0, take_profit: float | None = 110.0) -> dict[str, object]:
        return {
            "packet_type": "PROTECTIVE_ORDER_DRY_POLICY_REVIEW",
            "packet_version": "R136",
            "lane_key": LANE_KEY,
            "symbol": "BTCUSDT",
            "timeframe": "13m",
            "direction": "long",
            "entry_mode": "ladder_close_50_618",
            "risk_contract_hash": "risk-hash",
            "paper_proof_reference": "paper-proof",
            "entry_reference": 105.0,
            "stop_loss_policy": {
                "required": True,
                "reference": stop,
                "source": "paper proof",
                "direct_exchange_payload": None,
                "signed_request": None,
            },
            "take_profit_policy": {
                "required": True,
                "reference": take_profit,
                "source": "paper proof",
                "direct_exchange_payload": None,
                "signed_request": None,
            },
            "protective_order_mode": "LIVE_PROTECTIVE_ENABLED",
            "protective_policy_hash": "policy-hash",
        }

    def _connector_status(self) -> dict[str, object]:
        return {
            "connector_mode": "DRY_RUN_ONLY",
            "protective_order_mode": "LIVE_PROTECTIVE_ENABLED",
            "protective_orders_ready": True,
            "blockers": [],
        }

    def _protective_status(self) -> dict[str, object]:
        return {
            "protective_order_mode": "LIVE_PROTECTIVE_ENABLED",
            "protective_orders_ready": True,
            "blockers": [],
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
