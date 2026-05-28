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

from src.app.hammer_radar.operator.autonomous_paper_lane_executor_integration import (
    PAPER_EXECUTOR_INTEGRATION_PREVIEW,
    run_autonomous_paper_lane_executor_once,
)
from src.app.hammer_radar.operator.entry_mode_derivation_bridge import (
    CONFIRM_ENTRY_MODE_DERIVATION_BRIDGE_RECORDING_PHRASE,
    ENTRY_MODE_DERIVATION_BRIDGE_READY,
    ENTRY_MODE_DERIVATION_BRIDGE_RECORDED,
    ENTRY_MODE_DERIVATION_BRIDGE_REJECTED,
    EVENT_TYPE,
    LEDGER_FILENAME,
    PRIMARY_WATCHED_LANE,
    SAFETY,
    SECONDARY_WATCHED_LANE,
    append_entry_mode_derivation_bridge_record,
    build_entry_mode_derivation_bridge_status,
    derive_entry_mode_for_signal,
    derive_lane_key_for_signal,
    load_entry_mode_derivation_bridge_records,
    normalize_signal_for_watched_lane,
)
from src.app.hammer_radar.operator.signal_to_watcher_eligibility_trace import (
    build_signal_to_watcher_eligibility_trace,
)
from src.app.hammer_radar.operator.tiny_live_lane_unlock_contract import (
    EVENT_TYPE as UNLOCK_EVENT_TYPE,
    TINY_LIVE_LANE_UNLOCK_RECORDED,
    UNLOCKED_WAITING_FOR_CONDITIONS,
)
from src.app.hammer_radar.operator.strategy_performance import ELIGIBLE_FOR_FUTURE_TINY_LIVE


class EntryModeDerivationBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.log_dir = self.root / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.root / "lane_controls.json"
        self.now = datetime(2026, 5, 28, 12, 40, tzinfo=UTC)
        self.watched = [self._lane_spec(PRIMARY_WATCHED_LANE), self._lane_spec(SECONDARY_WATCHED_LANE)]
        self._write_config()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_preview_writes_no_bridge_record(self) -> None:
        self._write_unlock_contract([PRIMARY_WATCHED_LANE])
        self._write_signal(self._signal("13m", entry_mode=None))

        payload = build_entry_mode_derivation_bridge_status(
            log_dir=self.log_dir,
            trace_all_unlocked_lanes=True,
            now=self.now,
        )

        self.assertEqual(ENTRY_MODE_DERIVATION_BRIDGE_READY, payload["status"])
        self.assertFalse(payload["bridge_recorded"])
        self.assertFalse((self.log_dir / LEDGER_FILENAME).exists())

    def test_wrong_confirmation_rejects_recording(self) -> None:
        payload = build_entry_mode_derivation_bridge_status(
            log_dir=self.log_dir,
            trace_all_unlocked_lanes=True,
            record_bridge=True,
            confirm_bridge="wrong",
            now=self.now,
        )

        self.assertEqual(ENTRY_MODE_DERIVATION_BRIDGE_REJECTED, payload["status"])
        self.assertFalse(payload["confirmation_valid"])
        self.assertFalse(payload["bridge_recorded"])
        self.assertFalse((self.log_dir / LEDGER_FILENAME).exists())

    def test_exact_confirmation_records_bridge_diagnostic_only(self) -> None:
        self._write_unlock_contract([PRIMARY_WATCHED_LANE])
        self._write_signal(self._signal("13m", entry_mode=None))

        payload = build_entry_mode_derivation_bridge_status(
            log_dir=self.log_dir,
            trace_all_unlocked_lanes=True,
            record_bridge=True,
            confirm_bridge=CONFIRM_ENTRY_MODE_DERIVATION_BRIDGE_RECORDING_PHRASE,
            now=self.now,
        )
        records = load_entry_mode_derivation_bridge_records(log_dir=self.log_dir, limit=0)

        self.assertEqual(ENTRY_MODE_DERIVATION_BRIDGE_RECORDED, payload["status"])
        self.assertTrue(payload["bridge_recorded"])
        self.assertEqual(1, len(records))
        self.assertEqual(EVENT_TYPE, records[0]["event_type"])
        self.assertEqual(payload["bridge_id"], records[0]["bridge_id"])
        self.assertFalse(payload["safety"]["order_placed"])
        self.assertFalse(payload["safety"]["execution_attempted"])

    def test_null_entry_mode_for_13m_long_normalizes(self) -> None:
        normalized = normalize_signal_for_watched_lane(
            self._signal("13m", entry_mode=None),
            watched_lanes=self.watched,
            now=self.now,
        )

        self.assertEqual("ladder_close_50_618", derive_entry_mode_for_signal(normalized, watched_lanes=self.watched))
        self.assertEqual(PRIMARY_WATCHED_LANE, derive_lane_key_for_signal(normalized, watched_lanes=self.watched))
        self.assertTrue(normalized["derived_entry_mode"])
        self.assertEqual(PRIMARY_WATCHED_LANE, normalized["after_bridge_lane_key"])

    def test_null_entry_mode_for_44m_long_normalizes(self) -> None:
        normalized = normalize_signal_for_watched_lane(
            self._signal("44m", entry_mode=None),
            watched_lanes=self.watched,
            now=self.now,
        )

        self.assertTrue(normalized["derived_entry_mode"])
        self.assertEqual(SECONDARY_WATCHED_LANE, normalized["after_bridge_lane_key"])

    def test_non_watched_timeframe_does_not_normalize(self) -> None:
        normalized = normalize_signal_for_watched_lane(
            self._signal("8m", entry_mode=None),
            watched_lanes=self.watched,
            now=self.now,
        )

        self.assertIsNone(normalized["after_bridge_entry_mode"])
        self.assertFalse(normalized["bridge_would_match_watched_lane"])

    def test_watched_timeframe_short_direction_does_not_normalize(self) -> None:
        normalized = normalize_signal_for_watched_lane(
            self._signal("13m", direction="short", entry_mode=None),
            watched_lanes=self.watched,
            now=self.now,
        )

        self.assertIsNone(normalized["after_bridge_entry_mode"])
        self.assertFalse(normalized["bridge_would_match_watched_lane"])

    def test_existing_entry_mode_is_preserved(self) -> None:
        normalized = normalize_signal_for_watched_lane(
            self._signal("13m", entry_mode="manual_mode"),
            watched_lanes=self.watched,
            now=self.now,
        )

        self.assertEqual("manual_mode", normalized["after_bridge_entry_mode"])
        self.assertFalse(normalized["derived_entry_mode"])

    def test_stale_signal_remains_stale_after_normalization(self) -> None:
        normalized = normalize_signal_for_watched_lane(
            self._signal("13m", entry_mode=None, timestamp=(self.now - timedelta(minutes=20)).isoformat()),
            watched_lanes=self.watched,
            now=self.now,
        )

        self.assertEqual(PRIMARY_WATCHED_LANE, normalized["after_bridge_lane_key"])
        self.assertEqual("STALE", normalized["freshness_status_after_bridge"])
        self.assertEqual("candidate is stale", normalized["bridge_would_still_block_reason"])

    def test_normalization_does_not_create_paper_proof_directly(self) -> None:
        self._write_unlock_contract([PRIMARY_WATCHED_LANE])
        self._write_signal(self._signal("13m", entry_mode=None))

        payload = build_entry_mode_derivation_bridge_status(
            log_dir=self.log_dir,
            trace_all_unlocked_lanes=True,
            now=self.now,
        )

        self.assertTrue(payload["r142_effect_preview"]["does_not_force_paper_proof"])
        self.assertFalse((self.log_dir / "autonomous_paper_lane_executions.ndjson").exists())

    def test_r142_r129_integration_consumes_normalized_lane_key_for_fresh_candidate(self) -> None:
        payload = run_autonomous_paper_lane_executor_once(
            log_dir=self.log_dir,
            config_path=self.config_path,
            lane_key=PRIMARY_WATCHED_LANE,
            candidates=[self._signal("13m", entry_mode=None)],
            now=self.now,
            live_eligibility_matrix=self._matrix(),
            global_gate={"status": "FIRST_LIVE_BLOCKED", "execution_enabled_by_gate": False},
        )

        self.assertEqual(PAPER_EXECUTOR_INTEGRATION_PREVIEW, payload["status"])
        self.assertEqual(1, payload["paper_eligible_decisions_count"])
        self.assertEqual(PRIMARY_WATCHED_LANE, payload["candidate_decisions"][0]["lane_key"])

    def test_r144_trace_includes_after_bridge_fields(self) -> None:
        self._write_unlock_contract([PRIMARY_WATCHED_LANE])
        self._write_signal(self._signal("13m", entry_mode=None))

        payload = build_signal_to_watcher_eligibility_trace(
            log_dir=self.log_dir,
            trace_all_unlocked_lanes=True,
            now=self.now,
        )
        trace = payload["signal_traces"][0]

        self.assertIsNone(trace["before_bridge_entry_mode"])
        self.assertEqual("ladder_close_50_618", trace["after_bridge_entry_mode"])
        self.assertEqual(PRIMARY_WATCHED_LANE, trace["after_bridge_lane_key"])
        self.assertTrue(trace["bridge_would_match_watched_lane"])

    def test_safety_flags_always_false_except_paper_live_separation(self) -> None:
        payload = build_entry_mode_derivation_bridge_status(log_dir=self.log_dir, now=self.now)

        for key, value in payload["safety"].items():
            if key == "paper_live_separation_intact":
                self.assertTrue(value)
            else:
                self.assertFalse(value)

    def test_no_binance_order_payload_network_env_config_or_global_mutation(self) -> None:
        from src.app.hammer_radar.execution import binance_futures_connector

        before_env = dict(os.environ)
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
            payload = build_entry_mode_derivation_bridge_status(log_dir=self.log_dir, now=self.now)

        execute_live_order.assert_not_called()
        preview_payload.assert_not_called()
        protective_preview.assert_not_called()
        submit_test_order.assert_not_called()
        submit_protective_test.assert_not_called()
        build_signed_live_order_request.assert_not_called()
        build_signed_test_order_request.assert_not_called()
        build_signed_protective_order_requests.assert_not_called()
        self.assertEqual(before_env, dict(os.environ))
        self.assertFalse(payload["safety"]["config_written"])
        self.assertFalse(payload["safety"]["global_live_flags_changed"])

    def test_ledger_append_only(self) -> None:
        record = {
            "bridge_id": "bridge-1",
            "status": ENTRY_MODE_DERIVATION_BRIDGE_RECORDED,
            "watched_lanes": [],
            "normalization_rules": {},
            "recent_signal_bridge_summary": {},
            "normalized_signal_examples": [],
            "r142_effect_preview": {},
            "safety": SAFETY,
            "source_surfaces_used": [],
        }
        append_entry_mode_derivation_bridge_record(record, log_dir=self.log_dir)
        append_entry_mode_derivation_bridge_record({**record, "bridge_id": "bridge-2"}, log_dir=self.log_dir)
        records = load_entry_mode_derivation_bridge_records(log_dir=self.log_dir, limit=0)

        self.assertEqual(2, len(records))
        self.assertEqual(["bridge-1", "bridge-2"], [item["bridge_id"] for item in records])

    def test_cli_mode_exists(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "src.app.hammer_radar.operator.inspect", "--help"],
            check=True,
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": "."},
        )

        self.assertIn("entry-mode-derivation-bridge", result.stdout)

    def _write_signal(self, record: dict[str, object]) -> None:
        with (self.log_dir / "signals.ndjson").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    def _write_unlock_contract(self, lane_keys: list[str]) -> None:
        lanes = [self._lane_spec(lane_key) for lane_key in lane_keys]
        with (self.log_dir / "tiny_live_lane_unlock_contracts.ndjson").open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "event_type": UNLOCK_EVENT_TYPE,
                        "unlock_contract_id": "unlock-1",
                        "recorded_at_utc": self.now.isoformat(),
                        "status": TINY_LIVE_LANE_UNLOCK_RECORDED,
                        "lanes": lanes,
                        "operator_confirmation_valid": True,
                        "execution_state": UNLOCKED_WAITING_FOR_CONDITIONS,
                        "safety": SAFETY,
                    },
                    sort_keys=True,
                )
                + "\n"
            )

    def _signal(
        self,
        timeframe: str,
        *,
        direction: str = "long",
        entry_mode: str | None,
        timestamp: str | None = None,
    ) -> dict[str, object]:
        ts = timestamp or "2026-05-28T12:39:59.999000+00:00"
        return {
            "signal_id": f"BTCUSDT|{timeframe}|{direction}|{ts}",
            "candidate_id": f"BTCUSDT|{timeframe}|{direction}|{ts}",
            "symbol": "BTCUSDT",
            "timeframe": timeframe,
            "direction": direction,
            "timestamp": ts,
            "generated_at": ts,
            "entry_mode": entry_mode,
            "entry": 100.0,
            "stop": 99.0,
            "take_profit": 102.0,
            "score": 100,
        }

    def _write_config(self) -> None:
        self.config_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "default_mode": "disabled",
                    "notes": ["test"],
                    "lanes": [
                        self._lane("13m", "paper"),
                        self._lane("44m", "paper"),
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )

    def _lane(self, timeframe: str, mode: str) -> dict[str, object]:
        return {
            "symbol": "BTCUSDT",
            "timeframe": timeframe,
            "direction": "long",
            "entry_mode": "ladder_close_50_618",
            "mode": mode,
            "max_daily_trades": 3,
            "max_daily_loss_pct": 0.25,
            "freshness_seconds": 300,
            "cooldown_after_loss_minutes": 120,
            "require_protective_orders": True,
        }

    def _matrix(self) -> dict[str, object]:
        return {
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

    @staticmethod
    def _lane_spec(lane_key: str) -> dict[str, str]:
        symbol, timeframe, direction, entry_mode = lane_key.split("|")
        return {
            "lane_key": lane_key,
            "symbol": symbol,
            "timeframe": timeframe,
            "direction": direction,
            "entry_mode": entry_mode,
        }


if __name__ == "__main__":
    unittest.main()
