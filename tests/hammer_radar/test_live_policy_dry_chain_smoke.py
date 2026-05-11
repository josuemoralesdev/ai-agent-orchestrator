from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.archive import append_signal
from src.app.hammer_radar.operator.live_policy_dry_chain_smoke import (
    build_policy_armed_dry_chain_runbook,
    build_policy_armed_dry_chain_smoke_status,
    load_policy_armed_dry_chain_smokes,
    run_policy_armed_dry_chain_smoke,
)
from src.app.hammer_radar.operator.models import SignalRecord
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR
from src.app.hammer_radar.operator.telegram_operator_bridge import handle_telegram_operator_command


class LivePolicyDryChainSmokeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict("os.environ", {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False)
        self.env_patch.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_status_default_safe(self) -> None:
        payload = build_policy_armed_dry_chain_smoke_status(env={}, log_dir=self.log_dir)

        self.assertEqual("R75", payload["phase"])
        self.assertTrue(payload["dry_smoke_supported"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["execution_attempted"])
        self.assertFalse(payload["secrets_shown"])

    def test_micro_dry_smoke_no_candidate_blocks(self) -> None:
        payload = run_policy_armed_dry_chain_smoke(scenario="micro", log_dir=self.log_dir, env={}, persist=False)

        self.assertEqual("BLOCKED", payload["status"])
        self.assertIn("no queue-fresh micro candidate available", payload["blockers"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])

    def test_micro_dry_smoke_with_4m_candidate_reaches_intent_chain(self) -> None:
        signal_id = self._append_signal(timeframe="4m", age_minutes=1.0)

        payload = run_policy_armed_dry_chain_smoke(scenario="micro", log_dir=self.log_dir, env={}, persist=False)

        self.assertEqual("OK", payload["status"])
        self.assertEqual(signal_id, payload["selected_signal_id"])
        self.assertEqual("approve_signal", payload["steps"][1]["next_action"]["kind"])
        self.assertTrue(payload["chain_result"]["approval_found"])
        self.assertTrue(payload["chain_result"]["execution_intent_found"])
        self.assertEqual("run_rehearsal", payload["chain_result"]["next_action_kind"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["execution_attempted"])

    def test_higher_dry_smoke_no_candidate_blocks(self) -> None:
        payload = run_policy_armed_dry_chain_smoke(scenario="higher", log_dir=self.log_dir, env={}, persist=False)

        self.assertEqual("BLOCKED", payload["status"])
        self.assertIn("no queue-fresh higher-timeframe candidate available", payload["blockers"])
        self.assertFalse(payload["order_placed"])

    def test_higher_dry_smoke_with_444m_candidate_reaches_intent_chain(self) -> None:
        signal_id = self._append_signal(timeframe="444m", age_minutes=10.0)

        payload = run_policy_armed_dry_chain_smoke(scenario="higher", log_dir=self.log_dir, env={}, persist=False)

        self.assertEqual("OK", payload["status"])
        self.assertEqual(signal_id, payload["selected_signal_id"])
        self.assertEqual("approve_signal", payload["steps"][1]["next_action"]["kind"])
        self.assertTrue(payload["chain_result"]["approval_found"])
        self.assertTrue(payload["chain_result"]["execution_intent_found"])
        self.assertFalse(payload["real_order_placed"])

    def test_both_scenario_supports_partial_blocked(self) -> None:
        self._append_signal(timeframe="4m", age_minutes=1.0)

        payload = run_policy_armed_dry_chain_smoke(scenario="both", log_dir=self.log_dir, env={}, persist=False)

        self.assertEqual("OK", payload["status"])
        self.assertEqual("OK", payload["results"]["micro"]["status"])
        self.assertEqual("BLOCKED", payload["results"]["higher"]["status"])
        self.assertFalse(payload["order_placed"])

    def test_api_endpoints(self) -> None:
        self._append_signal(timeframe="4m", age_minutes=1.0)

        status = self.client.get("/live/policy-dry-chain/status").json()
        runbook = self.client.get("/live/policy-dry-chain/runbook").json()
        check = self.client.post("/live/policy-dry-chain/check", json={"scenario": "micro"}).json()

        self.assertEqual("OK", status["status"])
        self.assertEqual("OK", runbook["status"])
        self.assertEqual("OK", check["status"])
        for payload in (status, runbook, check):
            self.assertFalse(payload["order_placed"])
            self.assertFalse(payload["real_order_placed"])
            self.assertFalse(payload["secrets_shown"])

    def test_persistence_sanitized(self) -> None:
        self._append_signal(timeframe="4m", age_minutes=1.0)
        env = {
            LOG_DIR_ENV_VAR: str(self.log_dir),
            "TELEGRAM_BOT_TOKEN": "secret-token",
            "BINANCE_API_KEY": "secret-key",
            "BINANCE_API_SECRET": "secret-secret",
        }

        payload = run_policy_armed_dry_chain_smoke(scenario="micro", log_dir=self.log_dir, env=env, persist=True)
        records = load_policy_armed_dry_chain_smokes(log_dir=self.log_dir)
        rendered = str(records)

        self.assertEqual("OK", payload["status"])
        self.assertEqual(1, len(records))
        self.assertFalse(records[0]["order_placed"])
        self.assertFalse(records[0]["real_order_placed"])
        self.assertFalse(records[0]["secrets_shown"])
        self.assertNotIn("secret-token", rendered)
        self.assertNotIn("secret-key", rendered)
        self.assertNotIn("secret-secret", rendered)

    def test_telegram_commands(self) -> None:
        self._append_signal(timeframe="4m", age_minutes=1.0)
        policy = handle_telegram_operator_command(text="LIVE POLICY DRY SMOKE", log_dir=self.log_dir)
        micro = handle_telegram_operator_command(text="LIVE MICRO DRY SMOKE", log_dir=self.log_dir)
        higher = handle_telegram_operator_command(text="LIVE HIGHER DRY SMOKE", log_dir=self.log_dir)
        runbook = handle_telegram_operator_command(text="LIVE POLICY DRY RUNBOOK", log_dir=self.log_dir)
        raw_yes = handle_telegram_operator_command(text="YES", log_dir=self.log_dir)
        trade_now = handle_telegram_operator_command(text="trade now live", log_dir=self.log_dir)

        self.assertIn(policy["result_status"], {"ACCEPTED", "OK"})
        self.assertEqual("ACCEPTED", micro["result_status"])
        self.assertEqual("ACCEPTED", higher["result_status"])
        self.assertEqual("ACCEPTED", runbook["result_status"])
        for payload in (policy, micro, higher, runbook):
            self.assertIn("No order placed", payload["message"])
            self.assertFalse(payload["order_placed"])
            self.assertFalse(payload["real_order_placed"])
        self.assertEqual("REJECTED", raw_yes["result_status"])
        self.assertEqual("BLOCKED", trade_now["result_status"])

    def test_runbook_safe(self) -> None:
        payload = build_policy_armed_dry_chain_runbook(env={})

        self.assertEqual("R75", payload["phase"])
        self.assertIn("LIVE MICRO DRY SMOKE", payload["telegram_commands"])
        self.assertFalse(payload["order_placed"])

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


if __name__ == "__main__":
    unittest.main()
