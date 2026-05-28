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

from src.app.hammer_radar.operator.tiny_live_lane_unlock_contract import (
    CONFIRM_TINY_LIVE_LANE_UNLOCK_CONTRACT_PHRASE,
    DOES_NOT_AUTHORIZE,
    EVENT_TYPE,
    LEDGER_FILENAME,
    PRIMARY_UNLOCK_LANE,
    REQUIRED_FUTURE_CONDITIONS,
    SECONDARY_UNLOCK_LANE,
    TINY_LIVE_LANE_UNLOCK_PREVIEW,
    TINY_LIVE_LANE_UNLOCK_RECORDED,
    TINY_LIVE_LANE_UNLOCK_REJECTED,
    UNLOCKED_WAITING_FOR_CONDITIONS,
    build_default_unlock_lane_specs,
    build_lane_unlock_contract,
    build_lane_unlock_status,
    build_tiny_live_lane_unlock_contract_preview,
    load_lane_unlock_contract_records,
)


class TinyLiveLaneUnlockContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.tmp.name) / "logs"
        self.config_path = Path(self.tmp.name) / "lane_controls.json"
        self.now = datetime(2026, 5, 28, 12, 0, tzinfo=UTC)
        self.config_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "default_mode": "disabled",
                    "lanes": [
                        self._lane("13m", "armed_dry_run"),
                        self._lane("44m", "paper"),
                    ],
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_preview_writes_no_contract(self) -> None:
        payload = build_tiny_live_lane_unlock_contract_preview(
            log_dir=self.log_dir,
            config_path=self.config_path,
            unlock_all_recommended_lanes=True,
            now=self.now,
        )

        self.assertEqual(TINY_LIVE_LANE_UNLOCK_PREVIEW, payload["status"])
        self.assertFalse(payload["unlock_contract_recorded"])
        self.assertIsNone(payload["unlock_contract_id"])
        self.assertEqual("LOCKED", payload["execution_state"])
        self.assertFalse((self.log_dir / LEDGER_FILENAME).exists())

    def test_wrong_confirmation_rejects_record(self) -> None:
        payload = build_lane_unlock_contract(
            log_dir=self.log_dir,
            config_path=self.config_path,
            unlock_all_recommended_lanes=True,
            record_unlock_contract=True,
            confirm_unlock_contract="wrong",
            now=self.now,
        )

        self.assertEqual(TINY_LIVE_LANE_UNLOCK_REJECTED, payload["status"])
        self.assertFalse(payload["confirmation_valid"])
        self.assertFalse(payload["unlock_contract_recorded"])
        self.assertFalse((self.log_dir / LEDGER_FILENAME).exists())

    def test_exact_confirmation_records_unlock_contract_only(self) -> None:
        payload = build_lane_unlock_contract(
            log_dir=self.log_dir,
            config_path=self.config_path,
            unlock_all_recommended_lanes=True,
            record_unlock_contract=True,
            confirm_unlock_contract=CONFIRM_TINY_LIVE_LANE_UNLOCK_CONTRACT_PHRASE,
            now=self.now,
        )
        records = load_lane_unlock_contract_records(log_dir=self.log_dir, limit=0)

        self.assertEqual(TINY_LIVE_LANE_UNLOCK_RECORDED, payload["status"])
        self.assertTrue(payload["unlock_contract_recorded"])
        self.assertEqual(UNLOCKED_WAITING_FOR_CONDITIONS, payload["execution_state"])
        self.assertEqual(1, len(records))
        self.assertEqual(EVENT_TYPE, records[0]["event_type"])
        self.assertEqual(payload["unlock_contract_id"], records[0]["unlock_contract_id"])

    def test_default_lanes_include_13m_and_44m_ladder_close(self) -> None:
        specs = build_default_unlock_lane_specs()

        self.assertEqual([PRIMARY_UNLOCK_LANE, SECONDARY_UNLOCK_LANE], [spec["lane_key"] for spec in specs])
        self.assertEqual(["13m", "44m"], [spec["timeframe"] for spec in specs])
        self.assertEqual(["ladder_close_50_618", "ladder_close_50_618"], [spec["entry_mode"] for spec in specs])

    def test_contract_does_not_authorize_orders_binance_flags_or_kill_switch_disable(self) -> None:
        payload = build_lane_unlock_contract(
            log_dir=self.log_dir,
            config_path=self.config_path,
            lane_keys=[PRIMARY_UNLOCK_LANE],
            record_unlock_contract=True,
            confirm_unlock_contract=CONFIRM_TINY_LIVE_LANE_UNLOCK_CONTRACT_PHRASE,
            now=self.now,
        )

        for forbidden in ("order placement", "Binance order endpoint calls", "global live flag mutation", "kill switch disablement"):
            self.assertIn(forbidden, payload["does_not_authorize"])
        self.assertEqual(DOES_NOT_AUTHORIZE, payload["does_not_authorize"])
        self.assertFalse(payload["safety"]["order_placed"])
        self.assertFalse(payload["safety"]["real_order_placed"])
        self.assertFalse(payload["safety"]["execution_attempted"])
        self.assertFalse(payload["safety"]["global_live_flags_changed"])

    def test_required_future_conditions_include_fresh_candidate_and_protective_global_gates(self) -> None:
        payload = build_tiny_live_lane_unlock_contract_preview(
            log_dir=self.log_dir,
            config_path=self.config_path,
            unlock_all_recommended_lanes=True,
            now=self.now,
        )

        self.assertIn("fresh routed candidate", payload["required_future_conditions"])
        self.assertIn("protective policy clear", payload["required_future_conditions"])
        self.assertIn("global gates clear", payload["required_future_conditions"])
        self.assertEqual(REQUIRED_FUTURE_CONDITIONS, payload["required_future_conditions"])

    def test_status_only_reads_latest_contract(self) -> None:
        first = build_lane_unlock_contract(
            log_dir=self.log_dir,
            config_path=self.config_path,
            lane_keys=[PRIMARY_UNLOCK_LANE],
            record_unlock_contract=True,
            confirm_unlock_contract=CONFIRM_TINY_LIVE_LANE_UNLOCK_CONTRACT_PHRASE,
            now=self.now,
        )
        second = build_lane_unlock_contract(
            log_dir=self.log_dir,
            config_path=self.config_path,
            lane_keys=[SECONDARY_UNLOCK_LANE],
            record_unlock_contract=True,
            confirm_unlock_contract=CONFIRM_TINY_LIVE_LANE_UNLOCK_CONTRACT_PHRASE,
            now=self.now,
        )
        status = build_lane_unlock_status(log_dir=self.log_dir, now=self.now)

        self.assertEqual(UNLOCKED_WAITING_FOR_CONDITIONS, status["status"])
        self.assertEqual(second["unlock_contract_id"], status["unlock_contract_id"])
        self.assertNotEqual(first["unlock_contract_id"], status["unlock_contract_id"])
        self.assertEqual([SECONDARY_UNLOCK_LANE], [lane["lane_key"] for lane in status["lanes"]])

    def test_ledger_append_only(self) -> None:
        for lane_key in (PRIMARY_UNLOCK_LANE, SECONDARY_UNLOCK_LANE):
            build_lane_unlock_contract(
                log_dir=self.log_dir,
                config_path=self.config_path,
                lane_keys=[lane_key],
                record_unlock_contract=True,
                confirm_unlock_contract=CONFIRM_TINY_LIVE_LANE_UNLOCK_CONTRACT_PHRASE,
                now=self.now,
            )
        records = load_lane_unlock_contract_records(log_dir=self.log_dir, limit=0)

        self.assertEqual(2, len(records))
        self.assertEqual([PRIMARY_UNLOCK_LANE], [lane["lane_key"] for lane in records[0]["lanes"]])
        self.assertEqual([SECONDARY_UNLOCK_LANE], [lane["lane_key"] for lane in records[1]["lanes"]])

    def test_cli_exists(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--help",
            ],
            check=True,
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": "."},
        )

        self.assertIn("tiny-live-lane-unlock-contract", result.stdout)

    def test_no_binance_order_payload_network_env_global_or_config_mutation(self) -> None:
        from src.app.hammer_radar.execution import binance_futures_connector

        before_env = dict(os.environ)
        before_config = self.config_path.read_text(encoding="utf-8")
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
            payload = build_lane_unlock_contract(
                log_dir=self.log_dir,
                config_path=self.config_path,
                unlock_all_recommended_lanes=True,
                record_unlock_contract=True,
                apply_lane_mode_if_safe=True,
                confirm_unlock_contract=CONFIRM_TINY_LIVE_LANE_UNLOCK_CONTRACT_PHRASE,
                now=self.now,
            )

        execute_live_order.assert_not_called()
        preview_payload.assert_not_called()
        protective_preview.assert_not_called()
        submit_test_order.assert_not_called()
        submit_protective_test.assert_not_called()
        build_signed_live_order_request.assert_not_called()
        build_signed_test_order_request.assert_not_called()
        build_signed_protective_order_requests.assert_not_called()
        self.assertEqual(before_env, dict(os.environ))
        self.assertEqual(before_config, self.config_path.read_text(encoding="utf-8"))
        self.assertFalse(payload["safety"]["order_payload_created"])
        self.assertFalse(payload["safety"]["executable_payload_created"])
        self.assertFalse(payload["safety"]["protective_payload_created"])
        self.assertFalse(payload["safety"]["signed_request_created"])
        self.assertFalse(payload["safety"]["network_allowed"])
        self.assertFalse(payload["safety"]["env_mutated"])
        self.assertFalse(payload["safety"]["config_written"])
        self.assertFalse(payload["safety"]["global_live_flags_changed"])
        self.assertEqual("TINY_LIVE_LANE_UNLOCK_BLOCKED", payload["lane_mode_apply_result"]["status"])

    def _lane(self, timeframe: str, mode: str) -> dict[str, object]:
        return {
            "symbol": "BTCUSDT",
            "timeframe": timeframe,
            "direction": "long",
            "entry_mode": "ladder_close_50_618",
            "mode": mode,
            "max_daily_trades": 1,
            "max_daily_loss_pct": 0.25,
            "freshness_seconds": 120,
            "cooldown_after_loss_minutes": 120,
            "require_protective_orders": True,
        }
