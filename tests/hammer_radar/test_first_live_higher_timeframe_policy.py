from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.archive import append_signal
from src.app.hammer_radar.operator.first_live_candidate_queue import build_first_live_candidate_queue, select_first_live_candidate
from src.app.hammer_radar.operator.first_live_chain_runbook import build_first_live_chain_status
from src.app.hammer_radar.operator.first_live_higher_timeframe_policy import (
    evaluate_higher_timeframe_live_policy,
    get_higher_timeframe_live_policy,
)
from src.app.hammer_radar.operator.live_execution_intent import create_live_execution_intent
from src.app.hammer_radar.operator.models import SignalRecord
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR
from src.app.hammer_radar.operator.telegram_operator_bridge import handle_telegram_operator_command


class FirstLiveHigherTimeframePolicyTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict("os.environ", {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False)
        self.env_patch.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_policy_default_disabled(self) -> None:
        signal_id = self._append_signal(timeframe="444m", age_minutes=10.0)
        select_first_live_candidate(signal_id=signal_id, log_dir=self.log_dir, env={})

        queue = build_first_live_candidate_queue(log_dir=self.log_dir, env={})
        chain = build_first_live_chain_status(log_dir=self.log_dir, env={})

        self.assertFalse(queue["higher_timeframe_policy"]["higher_timeframe_live_allowed"])
        self.assertEqual(signal_id, queue["selected_signal_id"])
        self.assertFalse(queue["selection_status"]["candidate"]["live_candidate_allowed"])
        self.assertEqual("SELECTED_BUT_NOT_LIVE_ELIGIBLE", chain["status"])
        self.assertNotIn("LIVE APPROVE", str(chain["next_action"]))
        self.assertFalse(chain["order_placed"])
        self.assertFalse(chain["real_order_placed"])

    def test_policy_enabled_for_444m_emits_live_approve(self) -> None:
        env = self._enabled_env("444m")
        signal_id = self._append_signal(timeframe="444m", age_minutes=10.0)
        select_first_live_candidate(signal_id=signal_id, log_dir=self.log_dir, env=env)

        chain = build_first_live_chain_status(log_dir=self.log_dir, env=env)

        self.assertEqual(signal_id, chain["current_signal"]["signal_id"])
        self.assertTrue(chain["current_signal"]["higher_timeframe_profile"])
        self.assertEqual("higher_timeframe_policy", chain["current_signal"]["profile_match_reason"])
        self.assertEqual("WAITING_FOR_APPROVAL", chain["status"])
        self.assertEqual(f"LIVE APPROVE {signal_id}", chain["next_action"]["telegram_command"])
        self.assertFalse(chain["order_placed"])

    def test_policy_enabled_for_4h(self) -> None:
        env = self._enabled_env("4H")
        signal_id = self._append_signal(timeframe="4H", age_minutes=10.0)
        select_first_live_candidate(signal_id=signal_id, log_dir=self.log_dir, env=env)

        chain = build_first_live_chain_status(log_dir=self.log_dir, env=env)

        self.assertEqual("WAITING_FOR_APPROVAL", chain["status"])
        self.assertEqual(f"LIVE APPROVE {signal_id}", chain["next_action"]["telegram_command"])
        self.assertFalse(chain["real_order_placed"])

    def test_non_allowlisted_higher_timeframe_remains_blocked(self) -> None:
        env = self._enabled_env("444m,4H")
        signal_id = self._append_signal(timeframe="13H", age_minutes=10.0)
        select_first_live_candidate(signal_id=signal_id, log_dir=self.log_dir, env=env)

        queue = build_first_live_candidate_queue(log_dir=self.log_dir, env=env)
        chain = build_first_live_chain_status(log_dir=self.log_dir, env=env)

        self.assertFalse(queue["selection_status"]["candidate"]["live_candidate_allowed"])
        self.assertIn(queue["selection_status"]["candidate"]["policy_status"], {"CONTEXT_ONLY", "SELECTED_BUT_NOT_LIVE_ELIGIBLE"})
        self.assertEqual("SELECTED_BUT_NOT_LIVE_ELIGIBLE", chain["status"])
        self.assertNotIn("LIVE APPROVE", str(chain["next_action"]))

    def test_newer_micro_does_not_override_selected_enabled_444m(self) -> None:
        env = self._enabled_env("444m")
        signal_id = self._append_signal(timeframe="444m", age_minutes=10.0)
        select_first_live_candidate(signal_id=signal_id, log_dir=self.log_dir, env=env)
        self._append_signal(timeframe="8m", age_minutes=1.0)

        chain = build_first_live_chain_status(log_dir=self.log_dir, env=env)

        self.assertEqual(signal_id, chain["current_signal"]["signal_id"])
        self.assertEqual(f"LIVE APPROVE {signal_id}", chain["next_action"]["telegram_command"])
        self.assertFalse(chain["order_placed"])

    def test_live_approve_and_intent_compatible_for_enabled_444m(self) -> None:
        env = self._enabled_env("444m")
        signal_id = self._append_signal(timeframe="444m", age_minutes=10.0)
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
        self.assertNotIn("preview does not match signal_id", intent["blockers"])
        self.assertNotIn("timeframe not 13m", str(intent["blockers"]))
        self.assertFalse(intent["order_placed"])
        self.assertFalse(intent["real_order_placed"])

    def test_disabled_policy_blocks_approval_and_intent(self) -> None:
        signal_id = self._append_signal(timeframe="444m", age_minutes=10.0)
        with patch.dict("os.environ", {**self._disabled_env(), LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False):
            select_first_live_candidate(signal_id=signal_id, log_dir=self.log_dir)
            approval = handle_telegram_operator_command(text=f"LIVE APPROVE {signal_id}", log_dir=self.log_dir)
            with patch(
                "src.app.hammer_radar.operator.live_execution_intent.build_live_begins_status",
                return_value={"status": "READY_FOR_OPERATOR_APPROVAL"},
            ):
                intent = create_live_execution_intent(signal_id=signal_id, log_dir=self.log_dir, env=self._disabled_env())

        self.assertEqual("REJECTED", approval["result_status"])
        self.assertEqual("selected signal is not live-approvable under current policy", approval["reason"])
        self.assertNotEqual("INTENT_READY", intent["status"])
        self.assertFalse(intent["order_placed"])

    def test_existing_13m_and_44m_paths_preserved(self) -> None:
        signal_13m = self._append_signal(timeframe="13m", age_minutes=5.0)
        chain_13m = build_first_live_chain_status(log_dir=self.log_dir, env={})
        self.assertEqual(f"LIVE APPROVE {signal_13m}", chain_13m["next_action"]["telegram_command"])

        self._append_signal(timeframe="44m", age_minutes=10.0)
        queue = build_first_live_candidate_queue(log_dir=self.log_dir, env={})
        active = queue["buckets"]["active"][0]
        self.assertEqual("44m", active["timeframe"])
        self.assertTrue(active["live_candidate_allowed"])

    def test_policy_endpoint_and_telegram_command(self) -> None:
        endpoint = self.client.get("/live/higher-timeframe-policy/status").json()
        telegram = handle_telegram_operator_command(text="FIRST LIVE HIGHER POLICY", log_dir=self.log_dir)

        self.assertEqual("R72", endpoint["phase"])
        self.assertFalse(endpoint["higher_timeframe_live_allowed"])
        self.assertEqual("ACCEPTED", telegram["result_status"])
        self.assertIn("enabled=False", telegram["message"])
        self.assertFalse(telegram["order_placed"])
        self.assertFalse(telegram["real_order_placed"])

    def test_policy_helper_shapes(self) -> None:
        disabled = get_higher_timeframe_live_policy(env={})
        enabled_eval = evaluate_higher_timeframe_live_policy(
            {
                "signal_id": "sig",
                "symbol": "BTCUSDT",
                "timeframe": "444m",
                "direction": "long",
                "queue_fresh": True,
                "selected": True,
            },
            env=self._enabled_env("444m"),
        )

        self.assertFalse(disabled["higher_timeframe_live_allowed"])
        self.assertTrue(enabled_eval["candidate_allowed"])
        self.assertEqual("SELECTED_HIGHER_TIMEFRAME_ALLOWED", enabled_eval["candidate_policy_status"])
        self.assertFalse(enabled_eval["order_placed"])
        self.assertFalse(enabled_eval["secrets_shown"])

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

    def _enabled_env(self, timeframes: str) -> dict[str, str]:
        return {
            LOG_DIR_ENV_VAR: str(self.log_dir),
            "HAMMER_HIGHER_TIMEFRAME_LIVE_ALLOWED": "true",
            "HAMMER_HIGHER_TIMEFRAME_LIVE_TIMEFRAMES": timeframes,
        }

    def _disabled_env(self) -> dict[str, str]:
        return {
            LOG_DIR_ENV_VAR: str(self.log_dir),
            "HAMMER_HIGHER_TIMEFRAME_LIVE_ALLOWED": "false",
            "HAMMER_HIGHER_TIMEFRAME_LIVE_TIMEFRAMES": "444m,4H",
        }


if __name__ == "__main__":
    unittest.main()
