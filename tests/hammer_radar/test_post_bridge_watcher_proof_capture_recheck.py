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

from src.app.hammer_radar.operator.entry_mode_derivation_bridge import (
    ENTRY_MODE_DERIVATION_BRIDGE_RECORDED,
    PRIMARY_WATCHED_LANE,
    SAFETY as R145_SAFETY,
    SECONDARY_WATCHED_LANE,
    append_entry_mode_derivation_bridge_record,
)
from src.app.hammer_radar.operator.post_bridge_watcher_proof_capture_recheck import (
    BUILD_R147_AFTER_PAPER_PROOF_RECHECK,
    CAPTURE_PAPER_PROOF_AVAILABLE,
    CONFIRM_POST_BRIDGE_RECHECK_RECORDING_PHRASE,
    EVENT_TYPE,
    LEDGER_FILENAME,
    POST_BRIDGE_RECHECK_READY,
    POST_BRIDGE_RECHECK_RECORDED,
    POST_BRIDGE_RECHECK_REJECTED,
    RERUN_R145_TRACE,
    RUN_R142_WATCHER,
    SAFETY,
    WAIT_FOR_FRESH_NORMALIZED_CANDIDATE,
    append_post_bridge_recheck_record,
    build_post_bridge_watcher_proof_capture_recheck,
    load_post_bridge_recheck_records,
    post_bridge_recheck_records_path,
)
from src.app.hammer_radar.operator.tiny_live_lane_unlock_contract import (
    EVENT_TYPE as UNLOCK_EVENT_TYPE,
    TINY_LIVE_LANE_UNLOCK_RECORDED,
    UNLOCKED_WAITING_FOR_CONDITIONS,
)


class PostBridgeWatcherProofCaptureRecheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.tmp.name) / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.now = datetime(2026, 5, 28, 12, 40, tzinfo=UTC)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_preview_writes_no_recheck(self) -> None:
        self._write_unlock_contract([PRIMARY_WATCHED_LANE])
        self._write_bridge_record()
        self._write_signal(self._signal(timestamp=(self.now - timedelta(minutes=20)).isoformat()))

        payload = build_post_bridge_watcher_proof_capture_recheck(
            log_dir=self.log_dir,
            trace_all_unlocked_lanes=True,
            now=self.now,
        )

        self.assertEqual(POST_BRIDGE_RECHECK_READY, payload["status"])
        self.assertFalse(payload["trace_recorded"])
        self.assertFalse((self.log_dir / LEDGER_FILENAME).exists())

    def test_wrong_confirmation_rejects_record(self) -> None:
        self._write_unlock_contract([PRIMARY_WATCHED_LANE])
        self._write_bridge_record()

        payload = build_post_bridge_watcher_proof_capture_recheck(
            log_dir=self.log_dir,
            trace_all_unlocked_lanes=True,
            record_recheck=True,
            confirm_post_bridge_recheck="wrong",
            now=self.now,
        )

        self.assertEqual(POST_BRIDGE_RECHECK_REJECTED, payload["status"])
        self.assertFalse(payload["confirmation_valid"])
        self.assertFalse(payload["trace_recorded"])
        self.assertFalse((self.log_dir / LEDGER_FILENAME).exists())

    def test_exact_confirmation_records_recheck_only(self) -> None:
        self._write_unlock_contract([PRIMARY_WATCHED_LANE])
        self._write_bridge_record()
        self._write_signal(self._signal(timestamp=(self.now - timedelta(minutes=20)).isoformat()))

        payload = build_post_bridge_watcher_proof_capture_recheck(
            log_dir=self.log_dir,
            trace_all_unlocked_lanes=True,
            record_recheck=True,
            confirm_post_bridge_recheck=CONFIRM_POST_BRIDGE_RECHECK_RECORDING_PHRASE,
            now=self.now,
        )
        records = load_post_bridge_recheck_records(log_dir=self.log_dir, limit=0)

        self.assertEqual(POST_BRIDGE_RECHECK_RECORDED, payload["status"])
        self.assertTrue(payload["trace_recorded"])
        self.assertEqual(1, len(records))
        self.assertEqual(EVENT_TYPE, records[0]["event_type"])
        self.assertEqual(payload["recheck_id"], records[0]["recheck_id"])
        self.assertFalse(payload["safety"]["order_placed"])
        self.assertFalse(payload["safety"]["execution_attempted"])

    def test_if_r145_bridge_missing_rerun_r145_trace(self) -> None:
        self._write_unlock_contract([PRIMARY_WATCHED_LANE])
        self._write_signal(self._signal())

        payload = build_post_bridge_watcher_proof_capture_recheck(
            log_dir=self.log_dir,
            trace_all_unlocked_lanes=True,
            now=self.now,
        )

        self.assertEqual(RERUN_R145_TRACE, payload["next_operator_move"])
        self.assertFalse(payload["bridge_status"]["recorded_bridge_available"])

    def test_stale_normalized_candidates_wait_for_fresh_candidate(self) -> None:
        self._write_unlock_contract([PRIMARY_WATCHED_LANE])
        self._write_bridge_record()
        self._write_signal(self._signal(timestamp=(self.now - timedelta(minutes=20)).isoformat()))

        payload = build_post_bridge_watcher_proof_capture_recheck(
            log_dir=self.log_dir,
            trace_all_unlocked_lanes=True,
            now=self.now,
        )

        self.assertEqual(WAIT_FOR_FRESH_NORMALIZED_CANDIDATE, payload["next_operator_move"])
        self.assertEqual(1, payload["normalized_candidate_visibility"]["stale_normalized_count"])

    def test_fresh_normalized_mocked_candidate_can_run_watcher_or_capture(self) -> None:
        self._write_unlock_contract([PRIMARY_WATCHED_LANE])
        self._write_bridge_record()
        self._write_signal(self._signal())

        with patch(
            "src.app.hammer_radar.operator.post_bridge_watcher_proof_capture_recheck.run_autonomous_paper_lane_executor_once",
            return_value=self._paper_preview(eligible=1, blocked=0),
        ):
            payload = build_post_bridge_watcher_proof_capture_recheck(
                log_dir=self.log_dir,
                trace_all_unlocked_lanes=True,
                now=self.now,
            )

        self.assertIn(payload["next_operator_move"], {RUN_R142_WATCHER, CAPTURE_PAPER_PROOF_AVAILABLE})
        self.assertEqual(1, payload["normalized_candidate_visibility"]["fresh_normalized_count"])
        self.assertEqual(1, payload["paper_capture_readiness"]["paper_eligible_decisions_count"])

    def test_captured_proof_mocked_moves_to_r147(self) -> None:
        self._write_unlock_contract([PRIMARY_WATCHED_LANE])
        self._write_bridge_record()
        self._write_signal(self._signal())
        self._write_watch_capture()

        payload = build_post_bridge_watcher_proof_capture_recheck(
            log_dir=self.log_dir,
            trace_all_unlocked_lanes=True,
            now=self.now,
        )

        self.assertEqual(BUILD_R147_AFTER_PAPER_PROOF_RECHECK, payload["next_operator_move"])
        self.assertTrue(payload["paper_capture_readiness"]["paper_proof_captured"])

    def test_recommended_commands_are_safe_only(self) -> None:
        self._write_unlock_contract([PRIMARY_WATCHED_LANE])
        self._write_bridge_record()
        self._write_signal(self._signal(timestamp=(self.now - timedelta(minutes=20)).isoformat()))

        payload = build_post_bridge_watcher_proof_capture_recheck(
            log_dir=self.log_dir,
            trace_all_unlocked_lanes=True,
            now=self.now,
        )
        text = "\n".join(payload["recommended_commands"] + payload["do_not_run_yet"])

        self.assertIn("fresh-candidate-paper-proof-capture-loop", payload["recommended_commands"][0])
        self.assertIn("NO ORDER; NO BINANCE CALL", payload["recommended_commands"][0])
        self.assertNotIn("submit_test_order", text)
        self.assertNotIn("execute_live_order", text)
        self.assertNotIn("global-live-enable", text)

    def test_safety_flags_always_false_except_paper_live_separation(self) -> None:
        payload = build_post_bridge_watcher_proof_capture_recheck(log_dir=self.log_dir, now=self.now)

        for key, value in payload["safety"].items():
            if key == "paper_live_separation_intact":
                self.assertTrue(value)
            else:
                self.assertFalse(value)

    def test_no_binance_order_payload_network_env_config_or_global_mutation(self) -> None:
        from src.app.hammer_radar.execution import binance_futures_connector

        self._write_unlock_contract([PRIMARY_WATCHED_LANE])
        self._write_bridge_record()
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
            payload = build_post_bridge_watcher_proof_capture_recheck(log_dir=self.log_dir, now=self.now)

        execute_live_order.assert_not_called()
        preview_payload.assert_not_called()
        protective_preview.assert_not_called()
        submit_test_order.assert_not_called()
        submit_protective_test.assert_not_called()
        build_signed_live_order_request.assert_not_called()
        build_signed_test_order_request.assert_not_called()
        build_signed_protective_order_requests.assert_not_called()
        self.assertEqual(before_env, dict(os.environ))
        self.assertFalse(payload["safety"]["order_payload_created"])
        self.assertFalse(payload["safety"]["executable_payload_created"])
        self.assertFalse(payload["safety"]["protective_payload_created"])
        self.assertFalse(payload["safety"]["network_allowed"])
        self.assertFalse(payload["safety"]["env_mutated"])
        self.assertFalse(payload["safety"]["config_written"])
        self.assertFalse(payload["safety"]["global_live_flags_changed"])

    def test_ledger_append_only(self) -> None:
        record = {
            "status": POST_BRIDGE_RECHECK_RECORDED,
            "recheck_id": "recheck-1",
            "next_operator_move": RUN_R142_WATCHER,
            "why": "first",
            "safety": SAFETY,
        }
        append_post_bridge_recheck_record(record, log_dir=self.log_dir)
        append_post_bridge_recheck_record({**record, "recheck_id": "recheck-2"}, log_dir=self.log_dir)
        records = load_post_bridge_recheck_records(log_dir=self.log_dir, limit=0)

        self.assertEqual(2, len(records))
        self.assertEqual(["recheck-1", "recheck-2"], [item["recheck_id"] for item in records])
        self.assertEqual(self.log_dir / LEDGER_FILENAME, post_bridge_recheck_records_path(self.log_dir))

    def test_cli_exists(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "src.app.hammer_radar.operator.inspect", "--help"],
            check=True,
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": "."},
        )

        self.assertIn("post-bridge-watcher-proof-capture-recheck", result.stdout)

    def _write_bridge_record(self) -> None:
        append_entry_mode_derivation_bridge_record(
            {
                "bridge_id": "bridge-1",
                "status": ENTRY_MODE_DERIVATION_BRIDGE_RECORDED,
                "watched_lanes": [self._lane_spec(PRIMARY_WATCHED_LANE), self._lane_spec(SECONDARY_WATCHED_LANE)],
                "normalization_rules": {"does_not_bypass_freshness": True},
                "recent_signal_bridge_summary": {},
                "normalized_signal_examples": [],
                "r142_effect_preview": {"does_not_force_paper_proof": True},
                "safety": R145_SAFETY,
                "source_surfaces_used": [],
            },
            log_dir=self.log_dir,
        )

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

    def _write_watch_capture(self) -> None:
        with (self.log_dir / "fresh_candidate_paper_proof_capture_loop.ndjson").open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "event_type": "FRESH_CANDIDATE_PAPER_PROOF_CAPTURE_LOOP",
                        "watch_id": "watch-1",
                        "status": "FRESH_CANDIDATE_WATCH_CAPTURED_PAPER_PROOF",
                        "paper_proof_captured": True,
                        "captured_lane_key": PRIMARY_WATCHED_LANE,
                        "captured_evidence_ids": ["paper-1"],
                        "safety": SAFETY,
                    },
                    sort_keys=True,
                )
                + "\n"
            )

    def _signal(self, *, timestamp: str | None = None) -> dict[str, object]:
        ts = timestamp or "2026-05-28T12:39:59.999000+00:00"
        return {
            "signal_id": f"BTCUSDT|13m|long|{ts}",
            "candidate_id": f"BTCUSDT|13m|long|{ts}",
            "symbol": "BTCUSDT",
            "timeframe": "13m",
            "direction": "long",
            "timestamp": ts,
            "generated_at": ts,
            "entry_mode": None,
            "entry": 100.0,
            "stop": 99.0,
            "take_profit": 102.0,
            "score": 100,
        }

    @staticmethod
    def _paper_preview(*, eligible: int, blocked: int) -> dict[str, object]:
        return {
            "status": "PAPER_EXECUTOR_INTEGRATION_PREVIEW",
            "paper_eligible_decisions_count": eligible,
            "paper_blocked_decisions_count": blocked,
            "top_blockers": [],
            "safety": SAFETY,
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
