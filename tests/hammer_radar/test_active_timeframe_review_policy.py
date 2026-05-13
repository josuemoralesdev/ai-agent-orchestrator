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
    select_first_live_candidate,
)
from src.app.hammer_radar.operator.first_live_chain_runbook import build_first_live_chain_status
from src.app.hammer_radar.operator.first_live_timeframe_policy import (
    evaluate_first_live_timeframe_candidate,
    get_first_live_timeframe_policy,
)
from src.app.hammer_radar.operator.live_execution_intent import create_live_execution_intent
from src.app.hammer_radar.operator.live_policy_arming import build_live_policy_arming_runbook, build_live_policy_arming_status
from src.app.hammer_radar.operator.models import SignalRecord
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR
from src.app.hammer_radar.operator.telegram_operator_bridge import handle_telegram_operator_command


class ActiveTimeframeReviewPolicyTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict("os.environ", {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False)
        self.env_patch.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_default_policy_marks_22m_55m_active_but_not_approvable(self) -> None:
        policy = get_first_live_timeframe_policy(env={})

        self.assertFalse(policy["active_timeframe_live_allowed"])
        self.assertEqual(["22m", "55m"], policy["active_timeframe_live_timeframes"])
        self.assertEqual("active", policy["matrix"]["22m"]["category"])
        self.assertEqual("active", policy["matrix"]["55m"]["category"])
        self.assertEqual("ACTIVE_SELECTED_REVIEW_DISABLED", policy["matrix"]["22m"]["default_status"])
        self.assertEqual("ACTIVE_SELECTED_REVIEW", policy["profiles"]["ACTIVE_SELECTED_REVIEW"]["profile_name"])
        self.assertFalse(policy["order_placed"])
        self.assertFalse(policy["real_order_placed"])
        self.assertFalse(policy["secrets_shown"])

        for timeframe in ("22m", "55m"):
            with self.subTest(timeframe=timeframe):
                evaluation = evaluate_first_live_timeframe_candidate(
                    {
                        "signal_id": "sig",
                        "symbol": "BTCUSDT",
                        "timeframe": timeframe,
                        "direction": "long",
                        "queue_fresh": True,
                    },
                    env={},
                    selected=True,
                )
                self.assertEqual("active", evaluation["category"])
                self.assertEqual("ACTIVE_SELECTED_REVIEW", evaluation["profile_name"])
                self.assertEqual("ACTIVE_SELECTED_REVIEW_DISABLED", evaluation["policy_status"])
                self.assertFalse(evaluation["approval_allowed"])
                self.assertFalse(evaluation["order_placed"])

    def test_active_policy_enabled_allows_selected_22m_and_55m_only(self) -> None:
        env = self._active_env()
        for timeframe in ("22m", "55m"):
            with self.subTest(timeframe=timeframe):
                selected = evaluate_first_live_timeframe_candidate(
                    {
                        "signal_id": "sig",
                        "symbol": "BTCUSDT",
                        "timeframe": timeframe,
                        "direction": "long",
                        "queue_fresh": True,
                    },
                    env=env,
                    selected=True,
                )
                unselected = evaluate_first_live_timeframe_candidate(
                    {
                        "signal_id": "sig",
                        "symbol": "BTCUSDT",
                        "timeframe": timeframe,
                        "direction": "long",
                        "queue_fresh": True,
                    },
                    env=env,
                    selected=False,
                )

                self.assertEqual("ACTIVE_SELECTED_ALLOWED", selected["policy_status"])
                self.assertTrue(selected["approval_allowed"])
                self.assertFalse(unselected["approval_allowed"])
                self.assertIn("explicit candidate selection is required", unselected["blockers"])
                self.assertFalse(selected["real_order_placed"])

    def test_candidate_queue_shows_active_candidates_and_preserves_selected_22m(self) -> None:
        selected_id = self._append_signal(timeframe="22m", age_minutes=5.0)
        select_first_live_candidate(signal_id=selected_id, log_dir=self.log_dir, env={})
        newer_8m = self._append_signal(timeframe="8m", age_minutes=1.0)

        queue = build_first_live_candidate_queue(log_dir=self.log_dir, env={})
        chain = build_first_live_chain_status(log_dir=self.log_dir, env={})

        self.assertIn(selected_id, self._bucket_ids(queue, "active"))
        self.assertIn(newer_8m, self._bucket_ids(queue, "micro"))
        self.assertEqual(selected_id, chain["current_signal"]["signal_id"])
        self.assertEqual("ACTIVE_SELECTED_REVIEW", chain["current_signal"]["profile_name"])
        self.assertEqual("ACTIVE_SELECTED_REVIEW_DISABLED", chain["current_signal"]["policy_status"])
        self.assertNotIn("timeframe is blocked from live by strategy audit defaults", chain["current_signal"]["blockers"])
        self.assertEqual("SELECTED_BUT_NOT_LIVE_ELIGIBLE", chain["status"])
        self.assertNotIn("LIVE APPROVE", str(chain["next_action"]))
        self.assertFalse(chain["order_placed"])

    def test_first_live_next_active_disabled_and_enabled(self) -> None:
        signal_id = self._append_signal(timeframe="22m", age_minutes=5.0)
        select_first_live_candidate(signal_id=signal_id, log_dir=self.log_dir, env={})

        disabled = build_first_live_chain_status(log_dir=self.log_dir, env={})
        enabled = build_first_live_chain_status(log_dir=self.log_dir, env=self._active_env())

        self.assertEqual("SELECTED_BUT_NOT_LIVE_ELIGIBLE", disabled["status"])
        self.assertEqual("blocked", disabled["next_action"]["kind"])
        self.assertEqual("WAITING_FOR_APPROVAL", enabled["status"])
        self.assertEqual(f"LIVE APPROVE {signal_id}", enabled["next_action"]["telegram_command"])
        self.assertEqual("ACTIVE_SELECTED_ALLOWED", enabled["current_signal"]["policy_status"])
        self.assertEqual("fast", enabled["performance"]["mode"])
        self.assertFalse(enabled["real_order_placed"])

    def test_first_live_next_active_55m_enabled_emits_approve(self) -> None:
        env = self._active_env()
        signal_id = self._append_signal(timeframe="55m", age_minutes=10.0)
        select_first_live_candidate(signal_id=signal_id, log_dir=self.log_dir, env=env)

        payload = build_first_live_chain_status(log_dir=self.log_dir, env=env)

        self.assertEqual("WAITING_FOR_APPROVAL", payload["status"])
        self.assertEqual(f"LIVE APPROVE {signal_id}", payload["next_action"]["telegram_command"])
        self.assertFalse(payload["order_placed"])

    def test_approval_and_intent_block_when_disabled_and_progress_when_enabled(self) -> None:
        signal_id = self._append_signal(timeframe="22m", age_minutes=5.0)
        with patch.dict("os.environ", {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False):
            select_first_live_candidate(signal_id=signal_id, log_dir=self.log_dir)
            blocked_approval = handle_telegram_operator_command(text=f"LIVE APPROVE {signal_id}", log_dir=self.log_dir)
        self.assertEqual("REJECTED", blocked_approval["result_status"])

        self._clear_log_dir()
        env = self._active_env()
        signal_id = self._append_signal(timeframe="22m", age_minutes=5.0)
        with patch.dict("os.environ", env, clear=False):
            select_first_live_candidate(signal_id=signal_id, log_dir=self.log_dir)
            approval = handle_telegram_operator_command(text=f"LIVE APPROVE {signal_id}", log_dir=self.log_dir)
            with patch(
                "src.app.hammer_radar.operator.live_execution_intent.build_live_begins_status",
                return_value={"status": "READY_FOR_OPERATOR_APPROVAL"},
            ):
                intent = create_live_execution_intent(signal_id=signal_id, log_dir=self.log_dir, env=env)

        self.assertEqual("ACCEPTED", approval["result_status"])
        self.assertEqual("INTENT_READY", intent["status"])
        self.assertFalse(intent["order_placed"])
        self.assertFalse(intent["real_order_placed"])

    def test_api_and_policy_arming_surfaces_include_active_fields(self) -> None:
        status = self.client.get("/live/timeframe-policy/status").json()
        arming = build_live_policy_arming_status(env={})
        runbook = build_live_policy_arming_runbook(env={})

        self.assertIn("active_timeframe_live_allowed", status)
        self.assertIn("active_timeframe_live_timeframes", status)
        self.assertIn("active_timeframe_live_allowed", arming["policy_env"])
        self.assertIn("HAMMER_ACTIVE_TIMEFRAME_LIVE_ALLOWED=true", runbook["plans"]["active"]["manual_changes"])
        self.assertFalse(status["order_placed"])
        self.assertFalse(arming["real_order_placed"])
        self.assertFalse(runbook["secrets_shown"])

    def test_telegram_active_policy_commands_and_safety_blocks(self) -> None:
        signal_id = self._append_signal(timeframe="55m", age_minutes=10.0)

        timeframe = handle_telegram_operator_command(text="FIRST LIVE TIMEFRAME POLICY", log_dir=self.log_dir)
        active_policy = handle_telegram_operator_command(text="FIRST LIVE ACTIVE POLICY", log_dir=self.log_dir)
        selected = handle_telegram_operator_command(text=f"FIRST LIVE SELECT {signal_id}", log_dir=self.log_dir)
        selected_status = handle_telegram_operator_command(text="FIRST LIVE SELECTED", log_dir=self.log_dir)
        active_arming = handle_telegram_operator_command(text="LIVE ACTIVE ARMING", log_dir=self.log_dir)
        raw_yes = handle_telegram_operator_command(text="YES", log_dir=self.log_dir)
        trade_now = handle_telegram_operator_command(text="trade now live", log_dir=self.log_dir)

        self.assertEqual("ACCEPTED", timeframe["result_status"])
        self.assertIn("active_enabled", timeframe["message"])
        self.assertEqual("ACCEPTED", active_policy["result_status"])
        self.assertEqual("ACCEPTED", selected["result_status"])
        self.assertEqual("ACCEPTED", selected_status["result_status"])
        self.assertIn("ACTIVE_SELECTED_REVIEW_DISABLED", selected_status["message"])
        self.assertEqual("ACCEPTED", active_arming["result_status"])
        self.assertEqual("REJECTED", raw_yes["result_status"])
        self.assertEqual("BLOCKED", trade_now["result_status"])
        for payload in (timeframe, active_policy, selected, selected_status, active_arming, raw_yes, trade_now):
            self.assertFalse(payload["order_placed"])
            self.assertFalse(payload["real_order_placed"])
            self.assertFalse(payload["secrets_shown"])

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

    def _active_env(self) -> dict[str, str]:
        return {
            LOG_DIR_ENV_VAR: str(self.log_dir),
            "HAMMER_ACTIVE_TIMEFRAME_LIVE_ALLOWED": "true",
            "HAMMER_ACTIVE_TIMEFRAME_LIVE_TIMEFRAMES": "22m,55m",
        }

    def _bucket_ids(self, payload: dict, bucket: str) -> set[str]:
        return {item["signal_id"] for item in payload["buckets"][bucket]}

    def _clear_log_dir(self) -> None:
        for path in self.log_dir.iterdir():
            if path.is_file():
                path.unlink()


if __name__ == "__main__":
    unittest.main()
