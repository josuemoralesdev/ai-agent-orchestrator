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

from src.app.hammer_radar.operator.live_adapter_boundary_final_review import (
    CONFIRM_BOUNDARY_REVIEW_PHRASE,
    EVENT_TYPE,
    LEDGER_FILENAME,
    LIVE_ADAPTER_BOUNDARY_REVIEW_READY,
    LIVE_ADAPTER_BOUNDARY_REVIEW_REJECTED,
    append_live_adapter_boundary_review_record,
    build_live_adapter_boundary_final_review,
    build_live_adapter_boundary_final_review_cli_payload,
    inspect_credentials_boundary,
    inspect_network_boundary,
    inspect_order_payload_boundary,
    load_live_adapter_boundary_review_records,
)

LANE_KEY = "BTCUSDT|13m|long|ladder_close_50_618"


class LiveAdapterBoundaryFinalReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.log_dir = self.root / "logs"
        self.config_path = self.root / "lane_controls.json"
        self.now = datetime(2026, 5, 25, 18, 0, tzinfo=UTC)
        self._write_config("armed_dry_run")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_preview_writes_no_review_record(self) -> None:
        payload = self._review()

        self.assertEqual(LIVE_ADAPTER_BOUNDARY_REVIEW_READY, payload["status"])
        self.assertFalse((self.log_dir / LEDGER_FILENAME).exists())
        self.assertFalse(payload["safety"]["order_payload_created"])
        self.assertFalse(payload["safety"]["network_allowed"])

    def test_wrong_confirmation_rejects_recording(self) -> None:
        payload = build_live_adapter_boundary_final_review_cli_payload(
            log_dir=self.log_dir,
            lane_key=LANE_KEY,
            record_review=True,
            confirm_boundary_review="wrong",
        )

        self.assertEqual(LIVE_ADAPTER_BOUNDARY_REVIEW_REJECTED, payload["status"])
        self.assertFalse(payload["confirmation_valid"])
        self.assertFalse(payload["ledger_written"])
        self.assertFalse((self.log_dir / LEDGER_FILENAME).exists())

    def test_exact_confirmation_records_review_only(self) -> None:
        payload = build_live_adapter_boundary_final_review_cli_payload(
            log_dir=self.log_dir,
            lane_key=LANE_KEY,
            record_review=True,
            confirm_boundary_review=CONFIRM_BOUNDARY_REVIEW_PHRASE,
        )
        records = load_live_adapter_boundary_review_records(log_dir=self.log_dir, limit=0)

        self.assertEqual(LIVE_ADAPTER_BOUNDARY_REVIEW_READY, payload["status"])
        self.assertTrue(payload["ledger_written"])
        self.assertEqual(1, len(records))
        self.assertEqual(EVENT_TYPE, records[0]["event_type"])
        self.assertEqual(LANE_KEY, records[0]["lane_key"])
        self.assertFalse(records[0]["safety"]["order_placed"])
        self.assertFalse(records[0]["safety"]["real_order_placed"])
        self.assertFalse(records[0]["safety"]["execution_attempted"])
        self.assertFalse(records[0]["safety"]["order_payload_created"])
        self.assertFalse(records[0]["safety"]["network_allowed"])
        self.assertFalse(records[0]["safety"]["secrets_shown"])
        self.assertFalse(records[0]["safety"]["binance_order_endpoint_called"])
        self.assertFalse(records[0]["safety"]["signed_request_created"])

    def test_adapter_boundary_does_not_create_order_payload(self) -> None:
        payload = self._review()
        order_boundary = payload["boundary_reviews"]["order_payload_boundary"]

        self.assertFalse(order_boundary["r132_produced_order_payload"])
        self.assertFalse(order_boundary["order_payload_created"])
        self.assertFalse(order_boundary["signed_request_created"])
        self.assertFalse(payload["safety"]["order_payload_created"])

    def test_network_boundary_reports_no_network_used(self) -> None:
        boundary = inspect_network_boundary()

        self.assertFalse(boundary["r132_used_network"])
        self.assertFalse(boundary["network_allowed"])
        self.assertFalse(boundary["binance_order_endpoint_called"])
        self.assertTrue(boundary["future_live_adapter_requires_network"])

    def test_credential_boundary_reports_booleans_only_and_no_secrets(self) -> None:
        boundary = inspect_credentials_boundary(
            binance_status={
                "api_key_present": True,
                "api_secret_present": True,
                "live_env_file_exists": True,
            },
            connector_status={
                "api_key_present": True,
                "api_secret_present": True,
            },
        )

        self.assertIs(boundary["api_key_present"], True)
        self.assertIs(boundary["api_secret_present"], True)
        self.assertFalse(boundary["values_shown"])
        rendered = json.dumps(boundary)
        self.assertNotIn("supersecret", rendered)
        self.assertNotIn("abc123", rendered)

    def test_required_boundaries_and_future_requirements_included(self) -> None:
        payload = self._review()
        reviews = payload["boundary_reviews"]

        for key in (
            "adapter_module_boundary",
            "order_payload_boundary",
            "credential_boundary",
            "network_boundary",
            "protective_order_boundary",
            "kill_switch_boundary",
            "lane_authorization_boundary",
            "global_gate_boundary",
            "dry_authorization_readiness",
        ):
            self.assertIn(key, reviews)
        self.assertGreater(len(payload["future_dry_authorization_requirements"]), 0)
        self.assertIn("safe_command_pack", payload)

    def test_safety_flags_always_false_and_separation_true(self) -> None:
        payload = self._review()
        safety = payload["safety"]

        for key in (
            "order_placed",
            "real_order_placed",
            "execution_attempted",
            "order_payload_created",
            "network_allowed",
            "secrets_shown",
            "env_mutated",
            "config_written",
            "global_live_flags_changed",
            "binance_order_endpoint_called",
            "signed_request_created",
        ):
            self.assertFalse(safety[key])
        self.assertTrue(safety["paper_live_separation_intact"])

    def test_ledger_append_only(self) -> None:
        first = self._review()
        second = self._review()
        append_live_adapter_boundary_review_record(first, log_dir=self.log_dir)
        append_live_adapter_boundary_review_record(second, log_dir=self.log_dir)
        records = load_live_adapter_boundary_review_records(log_dir=self.log_dir, limit=0)

        self.assertEqual(2, len(records))
        self.assertNotEqual(records[0]["review_id"], records[1]["review_id"])

    def test_cli_mode_exists_and_returns_compact_status(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                str(self.log_dir),
                "live-adapter-boundary-final-review",
                "--lane-key",
                LANE_KEY,
            ],
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": "."},
        )

        payload = json.loads(result.stdout)
        self.assertEqual(LIVE_ADAPTER_BOUNDARY_REVIEW_READY, payload["status"])
        self.assertIn("boundary_reviews", payload)
        self.assertIn("main_blockers", payload)
        self.assertLess(len(result.stdout), 80000)

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
            payload = self._review()

        execute_live_order.assert_not_called()
        preview_payload.assert_not_called()
        protective_preview.assert_not_called()
        submit_test_order.assert_not_called()
        submit_protective_test.assert_not_called()
        build_signed_live_order_request.assert_not_called()
        build_signed_test_order_request.assert_not_called()
        build_signed_protective_order_requests.assert_not_called()
        self.assertFalse(payload["safety"]["binance_order_endpoint_called"])
        self.assertFalse(payload["safety"]["signed_request_created"])
        self.assertFalse(payload["safety"]["network_allowed"])

    def test_order_payload_boundary_has_future_requirements(self) -> None:
        boundary = inspect_order_payload_boundary(connector_status={})

        self.assertFalse(boundary["can_build_executable_payload_in_r132"])
        self.assertIn("execute_live_order", boundary["blocked_functions_not_called"])

    def _review(self) -> dict[str, object]:
        return build_live_adapter_boundary_final_review(
            log_dir=self.log_dir,
            lane_key=LANE_KEY,
            config_path=self.config_path,
            env={},
            now=self.now,
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


if __name__ == "__main__":
    unittest.main()
