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

from src.app.hammer_radar.operator.signal_to_watcher_eligibility_trace import (
    CONFIRM_SIGNAL_TO_WATCHER_TRACE_PHRASE,
    EVENT_TYPE,
    LEDGER_FILENAME,
    SAFETY,
    SIGNAL_DIRECTION_NOT_WATCHED,
    SIGNAL_MATCHES_TIMEFRAME_DIRECTION_BUT_ENTRY_MODE_MISMATCH,
    SIGNAL_MATCHES_WATCHED_LANE_AND_ELIGIBLE,
    SIGNAL_MATCHES_WATCHED_LANE_BUT_ENTRY_MODE_MISSING,
    SIGNAL_TIMEFRAME_NOT_WATCHED,
    SIGNAL_WATCHER_TRACE_READY,
    SIGNAL_WATCHER_TRACE_RECORDED,
    SIGNAL_WATCHER_TRACE_REJECTED,
    append_signal_to_watcher_trace_record,
    build_signal_to_watcher_eligibility_trace,
    build_unlocked_watched_lane_context,
    classify_signal_watcher_gap,
    load_signal_to_watcher_trace_records,
    signal_to_watcher_trace_records_path,
)
from src.app.hammer_radar.operator.tiny_live_lane_unlock_contract import (
    EVENT_TYPE as UNLOCK_EVENT_TYPE,
    PRIMARY_UNLOCK_LANE,
    SECONDARY_UNLOCK_LANE,
    TINY_LIVE_LANE_UNLOCK_RECORDED,
    UNLOCKED_WAITING_FOR_CONDITIONS,
)


class SignalToWatcherEligibilityTraceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.tmp.name) / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.now = datetime(2026, 5, 28, 12, 40, tzinfo=UTC)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_preview_writes_no_trace(self) -> None:
        self._write_signal(self._signal(entry_mode=None))

        payload = build_signal_to_watcher_eligibility_trace(
            log_dir=self.log_dir,
            trace_all_unlocked_lanes=True,
            now=self.now,
        )

        self.assertEqual(SIGNAL_WATCHER_TRACE_READY, payload["status"])
        self.assertFalse(payload["trace_recorded"])
        self.assertFalse((self.log_dir / LEDGER_FILENAME).exists())

    def test_wrong_confirmation_rejects_recording(self) -> None:
        self._write_signal(self._signal(entry_mode=None))

        payload = build_signal_to_watcher_eligibility_trace(
            log_dir=self.log_dir,
            record_trace=True,
            confirm_trace="wrong",
            now=self.now,
        )

        self.assertEqual(SIGNAL_WATCHER_TRACE_REJECTED, payload["status"])
        self.assertFalse(payload["confirmation_valid"])
        self.assertFalse(payload["trace_recorded"])
        self.assertFalse((self.log_dir / LEDGER_FILENAME).exists())

    def test_exact_confirmation_records_trace_only(self) -> None:
        self._write_signal(self._signal(entry_mode=None))

        payload = build_signal_to_watcher_eligibility_trace(
            log_dir=self.log_dir,
            record_trace=True,
            confirm_trace=CONFIRM_SIGNAL_TO_WATCHER_TRACE_PHRASE,
            now=self.now,
        )
        records = load_signal_to_watcher_trace_records(log_dir=self.log_dir, limit=0)

        self.assertEqual(SIGNAL_WATCHER_TRACE_RECORDED, payload["status"])
        self.assertTrue(payload["trace_recorded"])
        self.assertEqual(1, len(records))
        self.assertEqual(EVENT_TYPE, records[0]["event_type"])
        self.assertEqual(payload["trace_id"], records[0]["trace_id"])
        self.assertFalse(payload["safety"]["order_placed"])
        self.assertFalse(payload["safety"]["execution_attempted"])

    def test_unlocked_lanes_are_read_from_r143_status_when_available(self) -> None:
        self._write_unlock_contract([SECONDARY_UNLOCK_LANE])

        context = build_unlocked_watched_lane_context(
            log_dir=self.log_dir,
            trace_all_unlocked_lanes=True,
            now=self.now,
        )

        self.assertEqual("r143_unlock_contract", context["unlock_contract_status"]["source"])
        self.assertEqual([SECONDARY_UNLOCK_LANE], [lane["lane_key"] for lane in context["watched_lanes"]])

    def test_fallback_lanes_work_if_no_contract_exists(self) -> None:
        context = build_unlocked_watched_lane_context(log_dir=self.log_dir, now=self.now)

        self.assertTrue(context["unlock_contract_status"]["fallback_used"])
        self.assertEqual([PRIMARY_UNLOCK_LANE, SECONDARY_UNLOCK_LANE], [lane["lane_key"] for lane in context["watched_lanes"]])

    def test_signal_matching_watched_lane_with_null_entry_mode_classifies_as_missing(self) -> None:
        self._write_unlock_contract([PRIMARY_UNLOCK_LANE])
        self._write_signal(self._signal(entry_mode=None))

        payload = build_signal_to_watcher_eligibility_trace(log_dir=self.log_dir, trace_all_unlocked_lanes=True, now=self.now)

        self.assertEqual(
            SIGNAL_MATCHES_WATCHED_LANE_BUT_ENTRY_MODE_MISSING,
            payload["signal_traces"][0]["gap_classification"],
        )
        self.assertEqual([PRIMARY_UNLOCK_LANE], payload["signal_traces"][0]["possible_watched_lane_keys"])
        self.assertEqual([], payload["signal_traces"][0]["matched_watched_lane_keys"])

    def test_signal_with_non_watched_timeframe_classifies_as_timeframe_not_watched(self) -> None:
        self._write_unlock_contract([PRIMARY_UNLOCK_LANE])
        self._write_signal(self._signal(timeframe="8m", entry_mode=None))

        payload = build_signal_to_watcher_eligibility_trace(log_dir=self.log_dir, trace_all_unlocked_lanes=True, now=self.now)

        self.assertEqual(SIGNAL_TIMEFRAME_NOT_WATCHED, payload["signal_traces"][0]["gap_classification"])

    def test_signal_with_non_watched_direction_classifies_as_direction_not_watched(self) -> None:
        self._write_unlock_contract([PRIMARY_UNLOCK_LANE])
        self._write_signal(self._signal(direction="short", entry_mode=None))

        payload = build_signal_to_watcher_eligibility_trace(log_dir=self.log_dir, trace_all_unlocked_lanes=True, now=self.now)

        self.assertEqual(SIGNAL_DIRECTION_NOT_WATCHED, payload["signal_traces"][0]["gap_classification"])

    def test_signal_with_exact_lane_key_classifies_as_eligible_or_surface_dependent(self) -> None:
        self._write_unlock_contract([PRIMARY_UNLOCK_LANE])
        self._write_signal(self._signal(entry_mode="ladder_close_50_618"))
        self._write_scan(self._scan())

        payload = build_signal_to_watcher_eligibility_trace(log_dir=self.log_dir, trace_all_unlocked_lanes=True, now=self.now)

        self.assertIn(
            payload["signal_traces"][0]["gap_classification"],
            {
                SIGNAL_MATCHES_WATCHED_LANE_AND_ELIGIBLE,
                "SIGNAL_STALE_BY_WATCHER_RULES",
                "SIGNAL_FOUND_IN_SCAN_BUT_NOT_ROUTED",
                "SIGNAL_ROUTED_BUT_NOT_PAPER_ELIGIBLE",
                "SIGNAL_BLOCKED_BY_PAPER_EXECUTOR",
                "SIGNAL_BLOCKED_BY_LANE_MODE",
            },
        )
        self.assertEqual([PRIMARY_UNLOCK_LANE], payload["signal_traces"][0]["matched_watched_lane_keys"])

    def test_aggregate_gap_counts_and_best_next_move_are_included(self) -> None:
        self._write_unlock_contract([PRIMARY_UNLOCK_LANE])
        self._write_signal(self._signal(entry_mode=None))

        payload = build_signal_to_watcher_eligibility_trace(log_dir=self.log_dir, trace_all_unlocked_lanes=True, now=self.now)

        self.assertEqual(1, payload["aggregate_gap_counts"][SIGNAL_MATCHES_WATCHED_LANE_BUT_ENTRY_MODE_MISSING])
        self.assertIn("R145", payload["best_next_engineering_move"])

    def test_ledger_append_only(self) -> None:
        record = {
            "status": SIGNAL_WATCHER_TRACE_RECORDED,
            "trace_id": "trace-1",
            "watched_lanes": [],
            "trace_scope": {},
            "aggregate_gap_counts": {},
            "signal_traces": [],
            "best_next_engineering_move": "next",
            "recommended_next_commands": [],
            "safety": SAFETY,
            "source_surfaces_used": [],
        }
        append_signal_to_watcher_trace_record(record, log_dir=self.log_dir)
        append_signal_to_watcher_trace_record({**record, "trace_id": "trace-2"}, log_dir=self.log_dir)
        records = load_signal_to_watcher_trace_records(log_dir=self.log_dir, limit=0)

        self.assertEqual(2, len(records))
        self.assertEqual(["trace-1", "trace-2"], [record["trace_id"] for record in records])
        self.assertEqual(self.log_dir / LEDGER_FILENAME, signal_to_watcher_trace_records_path(self.log_dir))

    def test_cli_exists(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "src.app.hammer_radar.operator.inspect", "--help"],
            check=True,
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": "."},
        )

        self.assertIn("signal-to-watcher-eligibility-trace", result.stdout)

    def test_no_binance_order_payload_network_env_config_or_global_mutation(self) -> None:
        from src.app.hammer_radar.execution import binance_futures_connector

        self._write_signal(self._signal(entry_mode=None))
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
            payload = build_signal_to_watcher_eligibility_trace(log_dir=self.log_dir, now=self.now)

        execute_live_order.assert_not_called()
        preview_payload.assert_not_called()
        protective_preview.assert_not_called()
        submit_test_order.assert_not_called()
        submit_protective_test.assert_not_called()
        build_signed_live_order_request.assert_not_called()
        build_signed_test_order_request.assert_not_called()
        build_signed_protective_order_requests.assert_not_called()
        self.assertEqual(before_env, dict(os.environ))
        for key, value in payload["safety"].items():
            if key == "paper_live_separation_intact":
                self.assertTrue(value)
            else:
                self.assertFalse(value)

    def test_classify_exact_match_can_return_eligible(self) -> None:
        gap = classify_signal_watcher_gap(
            signal=self._signal(entry_mode="ladder_close_50_618"),
            watched_lanes=[
                {
                    "lane_key": PRIMARY_UNLOCK_LANE,
                    "symbol": "BTCUSDT",
                    "timeframe": "13m",
                    "direction": "long",
                    "entry_mode": "ladder_close_50_618",
                }
            ],
            paper_scan_match={"found": True},
            fresh_router_match={"route_status": "ROUTED_TO_LANE"},
            paper_executor_match={"paper_eligible_decisions_count": 1},
            unlock_contract_status={"fallback_used": False, "unlocked_lane_keys": [PRIMARY_UNLOCK_LANE]},
        )

        self.assertEqual(SIGNAL_MATCHES_WATCHED_LANE_AND_ELIGIBLE, gap)

    def test_classify_entry_mode_mismatch(self) -> None:
        gap = classify_signal_watcher_gap(
            signal=self._signal(entry_mode="fib_618"),
            watched_lanes=[
                {
                    "lane_key": PRIMARY_UNLOCK_LANE,
                    "symbol": "BTCUSDT",
                    "timeframe": "13m",
                    "direction": "long",
                    "entry_mode": "ladder_close_50_618",
                }
            ],
            paper_scan_match={},
            fresh_router_match={},
            paper_executor_match={},
            unlock_contract_status={},
        )

        self.assertEqual(SIGNAL_MATCHES_TIMEFRAME_DIRECTION_BUT_ENTRY_MODE_MISMATCH, gap)

    def _write_signal(self, record: dict[str, object]) -> None:
        with (self.log_dir / "signals.ndjson").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    def _write_scan(self, record: dict[str, object]) -> None:
        with (self.log_dir / "multi_symbol_paper_scans.ndjson").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    def _write_unlock_contract(self, lane_keys: list[str]) -> None:
        lanes = []
        for lane_key in lane_keys:
            symbol, timeframe, direction, entry_mode = lane_key.split("|")
            lanes.append(
                {
                    "lane_key": lane_key,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "direction": direction,
                    "entry_mode": entry_mode,
                }
            )
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
        *,
        symbol: str = "BTCUSDT",
        timeframe: str = "13m",
        direction: str = "long",
        entry_mode: str | None,
    ) -> dict[str, object]:
        timestamp = "2026-05-28T12:39:59.999000+00:00"
        return {
            "signal_id": f"{symbol}|{timeframe}|{direction}|{timestamp}",
            "symbol": symbol,
            "timeframe": timeframe,
            "direction": direction,
            "timestamp": timestamp,
            "entry_mode": entry_mode,
            "tradable": True,
        }

    def _scan(self) -> dict[str, object]:
        return {
            "scan_id": "scan-1",
            "created_at": "2026-05-28T12:40:00+00:00",
            "symbol": "BTCUSDT",
            "timeframe": "13m",
            "direction": "long",
            "latest_direction": "long",
            "latest_signal_timestamp": "2026-05-28T12:39:59.999000+00:00",
            "paper_signal_status": "PAPER_CANDIDATE",
            "score": 100,
            "tier": "HIGH_PRIORITY_WATCH",
        }


if __name__ == "__main__":
    unittest.main()
