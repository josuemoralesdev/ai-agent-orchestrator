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

from src.app.hammer_radar.operator.live_adapter_execution_rehearsal import (
    CONFIRM_ADAPTER_REHEARSAL_PHRASE,
    EVENT_TYPE,
    LEDGER_FILENAME,
    LIVE_ADAPTER_REHEARSAL_BLOCKED,
    LIVE_ADAPTER_REHEARSAL_PREVIEW,
    LIVE_ADAPTER_REHEARSAL_READY_FOR_FUTURE_IMPLEMENTATION,
    LIVE_ADAPTER_REHEARSAL_REJECTED,
    append_live_adapter_execution_rehearsal_record,
    build_forbidden_adapter_function_map,
    build_live_adapter_execution_rehearsal,
    load_live_adapter_execution_rehearsal_records,
)

LANE_KEY = "BTCUSDT|13m|long|ladder_close_50_618"


class LiveAdapterExecutionRehearsalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.log_dir = self.root / "logs"
        self.config_path = self.root / "lane_controls.json"
        self.now = datetime(2026, 5, 26, 13, 0, tzinfo=UTC)
        self._write_config("tiny_live")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_preview_writes_no_rehearsal_record(self) -> None:
        payload = self._rehearsal()

        self.assertIn(payload["status"], {LIVE_ADAPTER_REHEARSAL_PREVIEW, LIVE_ADAPTER_REHEARSAL_BLOCKED})
        self.assertFalse(payload["rehearsal_recorded"])
        self.assertFalse((self.log_dir / LEDGER_FILENAME).exists())

    def test_wrong_confirmation_rejects_recording(self) -> None:
        payload = self._rehearsal(record_rehearsal=True, confirm_adapter_rehearsal="wrong")

        self.assertEqual(LIVE_ADAPTER_REHEARSAL_REJECTED, payload["status"])
        self.assertFalse(payload["confirmation_valid"])
        self.assertFalse(payload["rehearsal_recorded"])
        self.assertFalse((self.log_dir / LEDGER_FILENAME).exists())

    def test_exact_confirmation_records_rehearsal_only_in_mocked_ready_state(self) -> None:
        payload = self._ready_rehearsal(
            record_rehearsal=True,
            confirm_adapter_rehearsal=CONFIRM_ADAPTER_REHEARSAL_PHRASE,
        )
        records = load_live_adapter_execution_rehearsal_records(log_dir=self.log_dir, limit=0)

        self.assertEqual(LIVE_ADAPTER_REHEARSAL_READY_FOR_FUTURE_IMPLEMENTATION, payload["status"])
        self.assertTrue(payload["rehearsal_recorded"])
        self.assertEqual(1, len(records))
        self.assertEqual(EVENT_TYPE, records[0]["event_type"])
        self.assertEqual(LANE_KEY, records[0]["lane_key"])
        self.assertFalse(records[0]["safety"]["order_placed"])
        self.assertFalse(records[0]["safety"]["real_order_placed"])
        self.assertFalse(records[0]["safety"]["execution_attempted"])
        self.assertFalse(records[0]["safety"]["order_payload_created"])
        self.assertFalse(records[0]["safety"]["executable_payload_created"])
        self.assertFalse(records[0]["safety"]["signed_request_created"])
        self.assertFalse(records[0]["safety"]["network_allowed"])

    def test_forbidden_function_map_includes_signing_network_and_execution_functions(self) -> None:
        rows = build_forbidden_adapter_function_map()
        by_name = {row["name"]: row for row in rows}

        self.assertEqual("SIGNING_FORBIDDEN", by_name["build_signed_live_order_request"]["classification"])
        self.assertEqual("NETWORK_FORBIDDEN", by_name["submit_test_order"]["classification"])
        self.assertEqual("EXECUTION_FORBIDDEN", by_name["execute_live_order"]["classification"])
        self.assertFalse(by_name["execute_live_order"]["called_in_r135"])
        self.assertFalse(by_name["execute_live_order"]["allowed_in_r135"])

    def test_payload_network_and_endpoint_safety_flags_are_false(self) -> None:
        payload = self._rehearsal()
        safety = payload["safety"]
        payload_boundary = payload["rehearsal_areas"]["payload_boundary"]
        network_boundary = payload["rehearsal_areas"]["network_boundary"]

        self.assertFalse(payload_boundary["executable_payload_created"])
        self.assertFalse(payload_boundary["order_payload_created"])
        self.assertFalse(payload_boundary["signed_request_created"])
        self.assertIsNone(payload_boundary["direct_exchange_payload"])
        self.assertFalse(network_boundary["binance_order_endpoint_called"])
        self.assertFalse(network_boundary["binance_test_order_endpoint_called"])
        self.assertFalse(network_boundary["protective_order_endpoint_called"])
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
            "protective_order_endpoint_called",
            "secrets_shown",
            "env_mutated",
            "config_written",
            "global_live_flags_changed",
        ):
            self.assertFalse(safety[key])
        self.assertTrue(safety["paper_live_separation_intact"])

    def test_credentials_are_booleans_only_and_no_values_shown(self) -> None:
        payload = self._rehearsal(env={"BINANCE_API_KEY": "abc123", "BINANCE_API_SECRET": "supersecret"})
        boundary = payload["rehearsal_areas"]["credential_boundary"]
        rendered = json.dumps(payload)

        self.assertIs(boundary["api_key_present"], True)
        self.assertIs(boundary["api_secret_present"], True)
        self.assertFalse(boundary["values_shown"])
        self.assertFalse(boundary["secrets_shown"])
        self.assertNotIn("abc123", rendered)
        self.assertNotIn("supersecret", rendered)

    def test_stop_conditions_include_global_protective_and_credential_blockers(self) -> None:
        payload = self._rehearsal(
            dry_authorization=self._dry(status="DRY_AUTHORIZATION_BLOCKED", credential=False, protective=False),
            r132_boundary_review=self._boundary(global_ready=False, protective_ready=False),
        )
        blocked = [condition for condition in payload["stop_conditions"] if condition["blocked"]]
        areas = {condition["area"] for condition in blocked}

        self.assertIn("global_gate_boundary", areas)
        self.assertIn("protective_boundary", areas)
        self.assertIn("credential_boundary", areas)
        self.assertGreaterEqual(len(payload["main_blockers"]), 3)

    def test_ledger_append_only(self) -> None:
        first = self._ready_rehearsal()
        second = self._ready_rehearsal()
        append_live_adapter_execution_rehearsal_record(
            {
                "event_type": EVENT_TYPE,
                "rehearsal_id": "first",
                "recorded_at_utc": self.now.isoformat(),
                "status": first["status"],
                "lane_key": LANE_KEY,
                "rehearsal_areas": first["rehearsal_areas"],
                "forbidden_function_map": first["forbidden_function_map"],
                "stop_conditions": first["stop_conditions"],
                "future_execution_adapter_requirements": first["future_execution_adapter_requirements"],
                "main_blockers": first["main_blockers"],
                "safety": first["safety"],
                "source_surfaces_used": first["source_surfaces_used"],
            },
            log_dir=self.log_dir,
        )
        append_live_adapter_execution_rehearsal_record(
            {
                "event_type": EVENT_TYPE,
                "rehearsal_id": "second",
                "recorded_at_utc": self.now.isoformat(),
                "status": second["status"],
                "lane_key": LANE_KEY,
                "rehearsal_areas": second["rehearsal_areas"],
                "forbidden_function_map": second["forbidden_function_map"],
                "stop_conditions": second["stop_conditions"],
                "future_execution_adapter_requirements": second["future_execution_adapter_requirements"],
                "main_blockers": second["main_blockers"],
                "safety": second["safety"],
                "source_surfaces_used": second["source_surfaces_used"],
            },
            log_dir=self.log_dir,
        )
        records = load_live_adapter_execution_rehearsal_records(log_dir=self.log_dir, limit=0)

        self.assertEqual(2, len(records))
        self.assertEqual(["first", "second"], [record["rehearsal_id"] for record in records])

    def test_cli_mode_exists_and_returns_compact_status(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                str(self.log_dir),
                "live-adapter-execution-rehearsal",
                "--lane-key",
                LANE_KEY,
            ],
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": "."},
        )

        payload = json.loads(result.stdout)
        self.assertIn(payload["status"], {LIVE_ADAPTER_REHEARSAL_PREVIEW, LIVE_ADAPTER_REHEARSAL_BLOCKED})
        self.assertIn("rehearsal_areas", payload)
        self.assertIn("forbidden_function_map", payload)
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
            payload = self._ready_rehearsal(
                record_rehearsal=True,
                confirm_adapter_rehearsal=CONFIRM_ADAPTER_REHEARSAL_PHRASE,
            )

        execute_live_order.assert_not_called()
        preview_payload.assert_not_called()
        protective_preview.assert_not_called()
        submit_test_order.assert_not_called()
        submit_protective_test.assert_not_called()
        build_signed_live_order_request.assert_not_called()
        build_signed_test_order_request.assert_not_called()
        build_signed_protective_order_requests.assert_not_called()
        self.assertFalse(payload["safety"]["binance_order_endpoint_called"])
        self.assertFalse(payload["safety"]["binance_test_order_endpoint_called"])
        self.assertFalse(payload["safety"]["protective_order_endpoint_called"])

    def _rehearsal(self, **kwargs: object) -> dict[str, object]:
        return build_live_adapter_execution_rehearsal(
            log_dir=self.log_dir,
            lane_key=LANE_KEY,
            config_path=self.config_path,
            env=kwargs.pop("env", {}),
            now=self.now,
            **kwargs,
        )

    def _ready_rehearsal(self, **kwargs: object) -> dict[str, object]:
        return self._rehearsal(
            dry_authorization=kwargs.pop("dry_authorization", self._dry(status="DRY_AUTHORIZATION_READY")),
            r132_boundary_review=kwargs.pop("r132_boundary_review", self._boundary(global_ready=True, protective_ready=True)),
            **kwargs,
        )

    def _dry(self, *, status: str, credential: bool = True, protective: bool = True) -> dict[str, object]:
        return {
            "status": status,
            "generated_at": self.now.isoformat(),
            "lane_key": LANE_KEY,
            "dry_authorization_packet": {
                "dry_authorization_hash": "r134-hash",
                "entry_intent": {"direct_exchange_payload": None, "signed_request": None},
                "protective_intent": {"direct_exchange_payload": None, "signed_request": None},
            },
            "prerequisites": {
                "credential_presence": {
                    "key_present": credential,
                    "signing_key_present": credential,
                    "values_shown": False,
                },
                "protective_readiness": {
                    "protective_orders_ready": protective,
                    "protective_order_mode": "LIVE_PROTECTIVE_ENABLED" if protective else "PREVIEW_ONLY",
                    "blockers": [] if protective else ["protective orders preview-only"],
                },
                "r131_rehearsal_status": "KILL_SWITCH_REHEARSAL_READY",
                "r106_gate_status": "FIRST_LIVE_ACTIVATION_READY",
            },
            "blockers": [] if status == "DRY_AUTHORIZATION_READY" else ["R134 blocked"],
            "safety": self._safe(),
        }

    def _boundary(self, *, global_ready: bool, protective_ready: bool) -> dict[str, object]:
        return {
            "status": "LIVE_ADAPTER_BOUNDARY_REVIEW_READY",
            "boundary_reviews": {
                "global_gate_boundary": {
                    "r106_status": "FIRST_LIVE_ACTIVATION_READY" if global_ready else "FIRST_LIVE_BLOCKED",
                    "final_live_preflight_status": "READY" if global_ready else "BLOCKED",
                    "live_env_boundary_status": "READY" if global_ready else "BLOCKED",
                    "live_arming_preflight_status": "READY" if global_ready else "BLOCKED",
                    "live_execution_enabled": False,
                    "live_orders_allowed": False,
                    "global_kill_switch": True,
                    "blockers": [] if global_ready else ["global gate blocked"],
                },
                "kill_switch_boundary": {
                    "r131_status": "KILL_SWITCH_REHEARSAL_READY",
                    "global_kill_switch_blocks_live_intent": True,
                    "lane_disable_blocks_live_intent": True,
                    "rollback_blocks_live_intent": True,
                    "blockers": [],
                },
                "protective_order_boundary": {
                    "protective_orders_ready": protective_ready,
                    "protective_order_mode": "LIVE_PROTECTIVE_ENABLED" if protective_ready else "PREVIEW_ONLY",
                    "stop_policy_ready": protective_ready,
                    "take_profit_policy_ready": protective_ready,
                    "blockers": [] if protective_ready else ["protective policy unresolved"],
                },
            },
            "main_blockers": [],
            "safety": self._safe(),
        }

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
            "protective_order_endpoint_called": False,
            "secrets_shown": False,
            "paper_live_separation_intact": True,
            "env_mutated": False,
            "config_written": False,
            "global_live_flags_changed": False,
        }


if __name__ == "__main__":
    unittest.main()
