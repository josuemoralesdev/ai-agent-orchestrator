from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.archive import append_signal
from src.app.hammer_radar.operator.first_live_candidate_queue import select_first_live_candidate
from src.app.hammer_radar.operator.first_live_chain_runbook import build_first_live_chain_status
from src.app.hammer_radar.operator.first_live_timeframe_policy import (
    evaluate_first_live_timeframe_candidate,
    get_first_live_timeframe_policy,
)
from src.app.hammer_radar.operator.live_execution_intent import create_live_execution_intent
from src.app.hammer_radar.operator.models import SignalRecord
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR
from src.app.hammer_radar.operator.telegram_operator_bridge import handle_telegram_operator_command


class FirstLiveTimeframePolicyTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict("os.environ", {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False)
        self.env_patch.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_default_policy_matrix_safe(self) -> None:
        policy = get_first_live_timeframe_policy(env={})

        self.assertEqual("R73", policy["phase"])
        self.assertFalse(policy["micro_live_allowed"])
        self.assertEqual("PAPER_ONLY", policy["matrix"]["4m"]["default_status"])
        self.assertEqual("PAPER_ONLY", policy["matrix"]["8m"]["default_status"])
        self.assertEqual("TINY_LIVE_ALLOWED", policy["matrix"]["13m"]["default_status"])
        self.assertEqual("TINY_LIVE_ALLOWED", policy["matrix"]["44m"]["default_status"])
        self.assertFalse(policy["higher_timeframe_live_allowed"])
        self.assertFalse(policy["order_placed"])
        self.assertFalse(policy["real_order_placed"])
        self.assertFalse(policy["secrets_shown"])

    def test_micro_disabled_selected_4m_does_not_emit_approve(self) -> None:
        signal_id = self._append_signal(timeframe="4m", age_minutes=1.0)
        select_first_live_candidate(signal_id=signal_id, log_dir=self.log_dir, env={})

        chain = build_first_live_chain_status(log_dir=self.log_dir, env={})

        self.assertEqual("SELECTED_BUT_NOT_LIVE_ELIGIBLE", chain["status"])
        self.assertIn(chain["current_signal"]["policy_status"], {"PAPER_ONLY", "PAPER_ONLY_SELECTED"})
        self.assertNotIn("LIVE APPROVE", str(chain["next_action"]))
        self.assertFalse(chain["order_placed"])

    def test_micro_enabled_selected_4m_and_8m_emit_approve(self) -> None:
        for timeframe in ("4m", "8m"):
            with self.subTest(timeframe=timeframe):
                self._clear_log_dir()
                env = self._micro_env()
                signal_id = self._append_signal(timeframe=timeframe, age_minutes=1.0)
                select_first_live_candidate(signal_id=signal_id, log_dir=self.log_dir, env=env)

                chain = build_first_live_chain_status(log_dir=self.log_dir, env=env)

                self.assertEqual("WAITING_FOR_APPROVAL", chain["status"])
                self.assertEqual(f"LIVE APPROVE {signal_id}", chain["next_action"]["telegram_command"])
                self.assertEqual("MICRO_SELECTED_ALLOWED", chain["current_signal"]["policy_status"])
                self.assertFalse(chain["real_order_placed"])

    def test_micro_enabled_still_requires_freshness(self) -> None:
        env = self._micro_env()
        signal_id = self._append_signal(timeframe="4m", age_minutes=5.0)
        self._write_selection(signal_id)

        chain = build_first_live_chain_status(log_dir=self.log_dir, env=env)

        self.assertNotEqual("WAITING_FOR_APPROVAL", chain["status"])
        self.assertNotIn("LIVE APPROVE", str(chain["next_action"]))
        self.assertFalse(chain["real_order_placed"])

    def test_tiny_and_higher_policy_preserved(self) -> None:
        tiny_id = self._append_signal(timeframe="13m", age_minutes=1.0)
        tiny_chain = build_first_live_chain_status(log_dir=self.log_dir, env={})
        self.assertEqual(f"LIVE APPROVE {tiny_id}", tiny_chain["next_action"]["telegram_command"])

        self._clear_log_dir()
        higher_id = self._append_signal(timeframe="444m", age_minutes=10.0)
        select_first_live_candidate(signal_id=higher_id, log_dir=self.log_dir, env={})
        disabled = build_first_live_chain_status(log_dir=self.log_dir, env={})
        self.assertEqual("SELECTED_BUT_NOT_LIVE_ELIGIBLE", disabled["status"])

        env = {LOG_DIR_ENV_VAR: str(self.log_dir), "HAMMER_HIGHER_TIMEFRAME_LIVE_ALLOWED": "true"}
        enabled = build_first_live_chain_status(log_dir=self.log_dir, env=env)
        self.assertEqual("WAITING_FOR_APPROVAL", enabled["status"])
        self.assertEqual(f"LIVE APPROVE {higher_id}", enabled["next_action"]["telegram_command"])

    def test_approval_and_intent_block_and_progress_for_micro(self) -> None:
        signal_id = self._append_signal(timeframe="4m", age_minutes=1.0)
        with patch.dict("os.environ", {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False):
            select_first_live_candidate(signal_id=signal_id, log_dir=self.log_dir)
            blocked_approval = handle_telegram_operator_command(text=f"LIVE APPROVE {signal_id}", log_dir=self.log_dir)
        self.assertEqual("REJECTED", blocked_approval["result_status"])

        self._clear_log_dir()
        env = self._micro_env()
        signal_id = self._append_signal(timeframe="4m", age_minutes=1.0)
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

    def test_telegram_and_api_policy_commands(self) -> None:
        endpoint = self.client.get("/live/timeframe-policy/status").json()
        timeframe = handle_telegram_operator_command(text="FIRST LIVE TIMEFRAME POLICY", log_dir=self.log_dir)
        micro = handle_telegram_operator_command(text="FIRST LIVE MICRO POLICY", log_dir=self.log_dir)
        higher = handle_telegram_operator_command(text="FIRST LIVE HIGHER POLICY", log_dir=self.log_dir)
        raw_yes = handle_telegram_operator_command(text="YES", log_dir=self.log_dir)
        trade_now = handle_telegram_operator_command(text="trade now live", log_dir=self.log_dir)

        self.assertEqual("OK", endpoint["status"])
        self.assertEqual("ACCEPTED", timeframe["result_status"])
        self.assertEqual("ACCEPTED", micro["result_status"])
        self.assertEqual("ACCEPTED", higher["result_status"])
        self.assertEqual("REJECTED", raw_yes["result_status"])
        self.assertEqual("BLOCKED", trade_now["result_status"])
        self.assertFalse(endpoint["order_placed"])
        self.assertFalse(endpoint["real_order_placed"])
        self.assertFalse(endpoint["secrets_shown"])

    def test_helper_evaluation_shape(self) -> None:
        disabled = evaluate_first_live_timeframe_candidate(
            {"signal_id": "sig", "symbol": "BTCUSDT", "timeframe": "4m", "direction": "long", "queue_fresh": True},
            env={},
            selected=True,
        )
        enabled = evaluate_first_live_timeframe_candidate(
            {"signal_id": "sig", "symbol": "BTCUSDT", "timeframe": "4m", "direction": "long", "queue_fresh": True},
            env={"HAMMER_MICRO_LIVE_ALLOWED": "true"},
            selected=True,
        )

        self.assertEqual("PAPER_ONLY", disabled["policy_status"])
        self.assertFalse(disabled["approval_allowed"])
        self.assertEqual("MICRO_SELECTED_ALLOWED", enabled["policy_status"])
        self.assertTrue(enabled["approval_allowed"])
        self.assertEqual("MICRO_SELECTED_REVIEW", enabled["profile_name"])

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

    def _micro_env(self) -> dict[str, str]:
        return {
            LOG_DIR_ENV_VAR: str(self.log_dir),
            "HAMMER_MICRO_LIVE_ALLOWED": "true",
            "HAMMER_MICRO_LIVE_TIMEFRAMES": "4m,8m",
        }

    def _write_selection(self, signal_id: str) -> None:
        (self.log_dir / "first_live_selected_signal.json").write_text(
            (
                '{"selected_signal_id": "%s", "selected_at": "%s", "source": "test", '
                '"reason": "test", "order_placed": false, "real_order_placed": false, "secrets_shown": false}\n'
            )
            % (signal_id, datetime.now(UTC).isoformat()),
            encoding="utf-8",
        )

    def _clear_log_dir(self) -> None:
        for path in self.log_dir.iterdir():
            if path.is_file():
                path.unlink()


if __name__ == "__main__":
    unittest.main()
