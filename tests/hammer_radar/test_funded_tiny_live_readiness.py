from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.funded_tiny_live_readiness import (
    build_funded_tiny_live_readiness_check,
    build_funded_tiny_live_readiness_runbook,
    build_funded_tiny_live_readiness_status,
    load_funded_tiny_live_readiness_checks,
)
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR
from src.app.hammer_radar.operator.telegram_operator_bridge import handle_telegram_operator_command


class FundedTinyLiveReadinessTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict("os.environ", {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False)
        self.env_patch.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_default_status_safe(self) -> None:
        payload = build_funded_tiny_live_readiness_status(env={}, log_dir=self.log_dir)

        self.assertEqual("R76", payload["phase"])
        self.assertIn(payload["status"], {"READY_FOR_POLICY_ARMING_ONLY", "NOT_READY_TO_FUND"})
        self.assertEqual(25.0, payload["funding_recommendation"]["minimum_operational_test_usdt"])
        self.assertEqual(50.0, payload["funding_recommendation"]["maximum_minimum_operational_test_usdt"])
        self.assertEqual(88.0, payload["funding_recommendation"]["preferred_initial_test_usdt"])
        self.assertEqual(100.0, payload["funding_recommendation"]["do_not_exceed_initial_funding_usdt"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["execution_attempted"])
        self.assertFalse(payload["secrets_shown"])

    def test_execution_enabled_blocks_funding_readiness(self) -> None:
        payload = build_funded_tiny_live_readiness_status(
            env={
                "HAMMER_LIVE_EXECUTION_ENABLED": "true",
                "HAMMER_ALLOW_LIVE_ORDERS": "true",
                "HAMMER_GLOBAL_KILL_SWITCH": "false",
            },
            log_dir=self.log_dir,
        )

        self.assertEqual("BLOCKED", payload["status"])
        self.assertTrue(any("HAMMER_LIVE_EXECUTION_ENABLED" in item for item in payload["blockers"]))
        self.assertFalse(payload["order_placed"])

    def test_dry_smoke_missing_not_ready_to_fund(self) -> None:
        payload = build_funded_tiny_live_readiness_status(env={}, log_dir=self.log_dir)

        self.assertNotEqual("READY_TO_FUND", payload["status"])
        self.assertTrue(any("R75 micro dry smoke" in item for item in payload["blockers"]))
        self.assertFalse(payload["ready_checks"]["dry_chain_smoke_recent"])

    def test_recent_dry_smoke_ok_ready_to_fund(self) -> None:
        self._write_smoke("micro")
        self._write_smoke("higher")

        payload = build_funded_tiny_live_readiness_status(env={}, log_dir=self.log_dir)

        self.assertEqual("READY_TO_FUND", payload["status"])
        self.assertTrue(payload["ready_checks"]["dry_chain_smoke_recent"])
        self.assertTrue(payload["ready_checks"]["live_execution_disabled"])
        self.assertTrue(payload["ready_checks"]["global_kill_switch_active"])
        self.assertFalse(payload["order_placed"])

    def test_runbook_contains_funding_limits_and_no_secrets(self) -> None:
        payload = build_funded_tiny_live_readiness_runbook(
            env={
                "TELEGRAM_BOT_TOKEN": "secret-token",
                "BINANCE_API_KEY": "secret-key",
                "BINANCE_API_SECRET": "secret-secret",
            },
            log_dir=self.log_dir,
        )
        rendered = str(payload)

        self.assertIn("88 USDT", str(payload["funding_steps"]))
        self.assertIn("444/888", str(payload["funding_steps"]))
        self.assertIn("Verify balance manually", str(payload["post_funding_steps"]))
        self.assertNotIn("secret-token", rendered)
        self.assertNotIn("secret-key", rendered)
        self.assertNotIn("secret-secret", rendered)
        self.assertFalse(payload["secrets_shown"])

    def test_api_endpoints(self) -> None:
        self._write_smoke("micro")
        status = self.client.get("/live/funding-readiness/status").json()
        runbook = self.client.get("/live/funding-readiness/runbook").json()
        check = self.client.post("/live/funding-readiness/check", json={}).json()

        self.assertEqual("R76", status["phase"])
        self.assertEqual("R76", runbook["phase"])
        self.assertEqual("R76", check["phase"])
        for payload in (status, runbook, check):
            self.assertFalse(payload["order_placed"])
            self.assertFalse(payload["real_order_placed"])
            self.assertFalse(payload["execution_attempted"])
            self.assertFalse(payload["secrets_shown"])

    def test_persistence_sanitized(self) -> None:
        env = {
            LOG_DIR_ENV_VAR: str(self.log_dir),
            "TELEGRAM_BOT_TOKEN": "secret-token",
            "BINANCE_API_KEY": "secret-key",
            "BINANCE_API_SECRET": "secret-secret",
        }

        payload = build_funded_tiny_live_readiness_check(env=env, log_dir=self.log_dir)
        records = load_funded_tiny_live_readiness_checks(log_dir=self.log_dir)
        rendered = str(records)

        self.assertTrue(payload["audit_event_recorded"])
        self.assertEqual(1, len(records))
        self.assertFalse(records[0]["order_placed"])
        self.assertFalse(records[0]["real_order_placed"])
        self.assertFalse(records[0]["execution_attempted"])
        self.assertFalse(records[0]["secrets_shown"])
        self.assertNotIn("secret-token", rendered)
        self.assertNotIn("secret-key", rendered)
        self.assertNotIn("secret-secret", rendered)

    def test_telegram_commands(self) -> None:
        readiness = handle_telegram_operator_command(text="LIVE FUNDING READINESS", log_dir=self.log_dir)
        runbook = handle_telegram_operator_command(text="LIVE FUNDING RUNBOOK", log_dir=self.log_dir)
        check = handle_telegram_operator_command(text="LIVE FUNDING CHECK", log_dir=self.log_dir)
        raw_yes = handle_telegram_operator_command(text="YES", log_dir=self.log_dir)
        trade_now = handle_telegram_operator_command(text="trade now live", log_dir=self.log_dir)

        for payload in (readiness, runbook, check):
            self.assertEqual("ACCEPTED", payload["result_status"])
            self.assertIn("No order placed", payload["message"])
            self.assertFalse(payload["order_placed"])
            self.assertFalse(payload["real_order_placed"])
            self.assertFalse(payload["secrets_shown"])
        self.assertEqual("REJECTED", raw_yes["result_status"])
        self.assertEqual("BLOCKED", trade_now["result_status"])

    def _write_smoke(self, scenario: str, *, created_at: datetime | None = None) -> None:
        path = self.log_dir / "live_policy_dry_chain_smokes.ndjson"
        created = created_at or datetime.now(UTC) - timedelta(minutes=10)
        record = {
            "smoke_id": f"smoke-{scenario}",
            "phase": "R75",
            "event_type": "live_policy_dry_chain_smoke",
            "created_at": created.isoformat(),
            "scenario": scenario,
            "status": "OK",
            "order_placed": False,
            "real_order_placed": False,
            "execution_attempted": False,
            "network_allowed": False,
            "secrets_shown": False,
            "blockers": [],
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


if __name__ == "__main__":
    unittest.main()
