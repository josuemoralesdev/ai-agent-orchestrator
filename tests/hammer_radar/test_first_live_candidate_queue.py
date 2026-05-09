from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.archive import append_signal
from src.app.hammer_radar.operator.first_live_candidate_queue import (
    build_first_live_candidate_queue,
    clear_selected_signal,
    load_selected_signal,
    select_first_live_candidate,
)
from src.app.hammer_radar.operator.first_live_chain_runbook import build_first_live_chain_status
from src.app.hammer_radar.operator.models import SignalRecord
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR
from src.app.hammer_radar.operator.telegram_operator_bridge import handle_telegram_operator_command


class FirstLiveCandidateQueueTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict("os.environ", {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False)
        self.env_patch.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_queue_includes_higher_timeframes_by_bucket(self) -> None:
        ids = {
            timeframe: self._append_signal(timeframe=timeframe, age_minutes=1.0)
            for timeframe in ("4m", "8m", "13m", "44m", "444m", "4H", "13H")
        }

        payload = build_first_live_candidate_queue(log_dir=self.log_dir, env={})

        self.assertEqual("R71", payload["phase"])
        self.assertIn(ids["4m"], self._bucket_ids(payload, "micro"))
        self.assertIn(ids["44m"], self._bucket_ids(payload, "active"))
        self.assertIn(ids["444m"], self._bucket_ids(payload, "swing"))
        self.assertIn(ids["4H"], self._bucket_ids(payload, "swing"))
        self.assertIn(ids["13H"], self._bucket_ids(payload, "macro"))
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["secrets_shown"])

    def test_newer_micro_signal_does_not_erase_selected_444m(self) -> None:
        selected_id = self._append_signal(timeframe="444m", age_minutes=10.0)
        self.assertEqual("ACCEPTED", select_first_live_candidate(signal_id=selected_id, log_dir=self.log_dir, env={})["status"])
        self._append_signal(timeframe="8m", age_minutes=1.0)

        payload = build_first_live_chain_status(log_dir=self.log_dir, env={})

        self.assertEqual(selected_id, payload["current_signal"]["signal_id"])
        self.assertEqual("r71_selected_candidate_queue", payload["current_signal"]["source"])
        self.assertEqual("SELECTED_BUT_NOT_LIVE_ELIGIBLE", payload["status"])
        self.assertNotIn("LIVE APPROVE", str(payload["next_action"]))
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])

    def test_selection_persists_and_status_shows_selected(self) -> None:
        signal_id = self._append_signal(timeframe="444m", age_minutes=10.0)

        result = select_first_live_candidate(signal_id=signal_id, log_dir=self.log_dir, source="telegram", reason="test", env={})
        status = build_first_live_candidate_queue(log_dir=self.log_dir, env={})
        state = load_selected_signal(log_dir=self.log_dir)

        self.assertEqual("ACCEPTED", result["status"])
        self.assertEqual(signal_id, state["selected_signal_id"])
        self.assertEqual(signal_id, status["selected_signal_id"])
        self.assertEqual("SELECTED_BUT_NOT_LIVE_ELIGIBLE", status["selection_status"]["status"])

    def test_clear_selection_removes_state(self) -> None:
        signal_id = self._append_signal(timeframe="444m", age_minutes=10.0)
        select_first_live_candidate(signal_id=signal_id, log_dir=self.log_dir, env={})

        result = clear_selected_signal(log_dir=self.log_dir, env={})

        self.assertEqual("CLEARED", result["status"])
        self.assertIsNone(load_selected_signal(log_dir=self.log_dir))

    def test_unknown_selection_rejected(self) -> None:
        result = select_first_live_candidate(signal_id="bogus", log_dir=self.log_dir, env={})

        self.assertEqual("REJECTED", result["status"])
        self.assertFalse(result["order_placed"])
        self.assertFalse(result["real_order_placed"])

    def test_expired_selected_signal_does_not_approve(self) -> None:
        signal_id = self._append_signal(timeframe="444m", age_minutes=445.0)
        self._write_selection(signal_id)

        payload = build_first_live_chain_status(log_dir=self.log_dir, env={})
        queue = build_first_live_candidate_queue(log_dir=self.log_dir, env={})

        self.assertNotEqual("r71_selected_candidate_queue", payload["current_signal"]["source"])
        self.assertFalse(payload["current_signal"]["fresh"])
        self.assertNotIn("LIVE APPROVE", str(payload["next_action"]))
        self.assertIsNone(queue["selected_signal_id"])

    def test_policy_blocks_higher_timeframe_live_approval_by_default(self) -> None:
        signal_id = self._append_signal(timeframe="4H", age_minutes=10.0)
        select_first_live_candidate(signal_id=signal_id, log_dir=self.log_dir, env={})

        payload = build_first_live_chain_status(log_dir=self.log_dir, env={})

        self.assertEqual(signal_id, payload["current_signal"]["signal_id"])
        self.assertEqual("SELECTED_BUT_NOT_LIVE_ELIGIBLE", payload["status"])
        self.assertEqual("blocked", payload["next_action"]["kind"])
        self.assertNotIn("LIVE APPROVE", str(payload["next_action"]))

    def test_existing_tiny_live_path_preserved_without_selection(self) -> None:
        signal_id = self._append_signal(timeframe="13m", age_minutes=5.0)

        payload = build_first_live_chain_status(log_dir=self.log_dir, env={})

        self.assertEqual(signal_id, payload["current_signal"]["signal_id"])
        self.assertEqual("WAITING_FOR_APPROVAL", payload["status"])
        self.assertEqual(f"LIVE APPROVE {signal_id}", payload["next_action"]["telegram_command"])

    def test_telegram_candidate_commands_and_safety_blocks(self) -> None:
        signal_id = self._append_signal(timeframe="444m", age_minutes=10.0)

        candidates = handle_telegram_operator_command(text="FIRST LIVE CANDIDATES", log_dir=self.log_dir)
        selected = handle_telegram_operator_command(text=f"FIRST LIVE SELECT {signal_id}", log_dir=self.log_dir)
        selected_status = handle_telegram_operator_command(text="FIRST LIVE SELECTED", log_dir=self.log_dir)
        raw_yes = handle_telegram_operator_command(text="YES", log_dir=self.log_dir)
        trade_now = handle_telegram_operator_command(text="trade now live", log_dir=self.log_dir)
        cleared = handle_telegram_operator_command(text="FIRST LIVE CLEAR", log_dir=self.log_dir)

        self.assertEqual("ACCEPTED", candidates["result_status"])
        self.assertEqual("ACCEPTED", selected["result_status"])
        self.assertEqual("ACCEPTED", selected_status["result_status"])
        self.assertIn("not live-approvable", selected_status["message"])
        self.assertEqual("REJECTED", raw_yes["result_status"])
        self.assertEqual("BLOCKED", trade_now["result_status"])
        self.assertEqual("ACCEPTED", cleared["result_status"])
        for payload in (candidates, selected, selected_status, raw_yes, trade_now, cleared):
            self.assertFalse(payload["order_placed"])
            self.assertFalse(payload["real_order_placed"])
            self.assertFalse(payload["secrets_shown"])

    def test_api_endpoints_are_no_order(self) -> None:
        signal_id = self._append_signal(timeframe="444m", age_minutes=10.0)

        status = self.client.get("/live/first-candidates/status").json()
        selected = self.client.post("/live/first-candidates/select", json={"signal_id": signal_id}).json()
        cleared = self.client.post("/live/first-candidates/clear", json={}).json()

        self.assertEqual("OK", status["status"])
        self.assertEqual("ACCEPTED", selected["status"])
        self.assertEqual("CLEARED", cleared["status"])
        for payload in (status, selected, cleared):
            self.assertFalse(payload["order_placed"])
            self.assertFalse(payload["real_order_placed"])
            self.assertFalse(payload["secrets_shown"])

    def _bucket_ids(self, payload: dict, bucket: str) -> set[str]:
        return {item["signal_id"] for item in payload["buckets"][bucket]}

    def _append_signal(self, *, timeframe: str, age_minutes: float, direction: str = "long") -> str:
        timestamp = (datetime.now(UTC) - timedelta(minutes=age_minutes)).isoformat()
        signal_id = f"BTCUSDT|{timeframe}|{direction}|{timestamp}"
        append_signal(
            SignalRecord(
                signal_id=signal_id,
                symbol="BTCUSDT",
                timeframe=timeframe,
                direction=direction,
                timestamp=timestamp,
                hammer_strength=91.0,
                hammer_high=101.0,
                hammer_low=99.0,
                fib_50=100.0,
                fib_618=101.0,
                fib_650=101.5,
                fib_786=102.0,
                invalidation=98.0,
                bias_timeframe="4h",
                bias_direction="long",
                bias_aligned=True,
                same_direction_streak=1,
                opposite_direction_streak=0,
                tradable=True,
            ),
            log_dir=self.log_dir,
        )
        return signal_id

    def _write_selection(self, signal_id: str) -> None:
        path = self.log_dir / "first_live_selected_signal.json"
        path.write_text(
            (
                '{"selected_signal_id": "%s", "selected_at": "%s", "source": "test", '
                '"reason": "test", "order_placed": false, "real_order_placed": false, "secrets_shown": false}\n'
            )
            % (signal_id, datetime.now(UTC).isoformat()),
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
