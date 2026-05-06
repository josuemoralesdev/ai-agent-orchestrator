from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator import archive
from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.live_approval import evaluate_live_approval_request
from src.app.hammer_radar.operator.live_approval import append_live_approval_request
from src.app.hammer_radar.operator.live_begins import (
    build_live_begins_status,
    evaluate_and_record_live_begins,
    load_live_begins_events,
)
from src.app.hammer_radar.operator.models import OutcomeRecord, SignalRecord
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR
from src.app.hammer_radar.operator.telegram_operator_bridge import handle_telegram_operator_command


class LiveBeginsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict("os.environ", {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False)
        self.env_patch.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_default_safety_state_blocks_without_candidate(self) -> None:
        payload = build_live_begins_status(log_dir=self.log_dir, env={})

        self.assertIn(payload["status"], {"BLOCKED", "NOT_READY"})
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["would_place_order"])
        self.assertFalse(payload["secrets_shown"])
        self.assertIn("candidate missing", payload["blockers"])
        self.assertFalse(payload["checks"]["candidate_present"])

    def test_live_flags_enabled_but_kill_switch_active_still_blocks(self) -> None:
        self._seed_ready_candidate()
        env = self._live_env(kill_switch=True, protective_enabled=True)

        payload = build_live_begins_status(log_dir=self.log_dir, env=env)

        self.assertEqual("BLOCKED", payload["status"])
        self.assertIn("global kill switch active", payload["blockers"])
        self.assertFalse(payload["checks"]["global_kill_switch_off"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])

    def test_live_flags_kill_switch_off_but_no_approval_waits_when_other_gates_pass(self) -> None:
        signal_id = self._seed_ready_candidate()
        env = self._live_env(kill_switch=False, protective_enabled=True)

        payload = build_live_begins_status(log_dir=self.log_dir, env=env)

        self.assertEqual(signal_id, payload["latest_signal_id"])
        self.assertEqual("READY_FOR_OPERATOR_APPROVAL", payload["status"])
        self.assertIn("operator approval missing", payload["blockers"])
        self.assertFalse(payload["checks"]["operator_approved"])
        self.assertFalse(payload["order_placed"])

    def test_approval_present_but_stale_candidate_blocks_due_stale(self) -> None:
        self._seed_promoted_strategy(samples=30)
        stale_signal = self._eligible_signal(
            signal_id="BTCUSDT|13m|long|2026-05-05T10:31:00+00:00",
            timestamp=(datetime.now(UTC) - timedelta(hours=2)).isoformat(),
        )
        archive.append_signal(stale_signal, log_dir=self.log_dir)
        append_live_approval_request(
            {
                "request_id": "stale-approval",
                "created_at": datetime.now(UTC).isoformat(),
                "normalized_action": "live_approve_exact",
                "parse_status": "ACCEPTED",
                "signal_id": stale_signal.signal_id,
                "approval_gate_status": "READY_BUT_EXECUTION_DISABLED",
                "order_placed": False,
                "real_order_placed": False,
                "secrets_shown": False,
            },
            log_dir=self.log_dir,
        )
        env = self._live_env(kill_switch=False, protective_enabled=True)

        payload = build_live_begins_status(log_dir=self.log_dir, env=env)

        self.assertEqual("BLOCKED", payload["status"])
        self.assertEqual("stale", payload["freshness_status"])
        self.assertIn("candidate stale", payload["blockers"])
        self.assertFalse(payload["order_placed"])

    def test_all_gates_pass_is_eligible_but_no_order_is_placed(self) -> None:
        signal_id = self._seed_ready_candidate()
        approval = evaluate_live_approval_request(text=f"LIVE APPROVE {signal_id}", log_dir=self.log_dir)
        env = self._live_env(kill_switch=False, protective_enabled=True)

        payload = build_live_begins_status(log_dir=self.log_dir, env=env)

        self.assertEqual("READY_BUT_EXECUTION_DISABLED", approval["approval_gate_status"])
        self.assertEqual("ELIGIBLE_TINY_LIVE", payload["status"])
        self.assertTrue(payload["checks"]["operator_approved"])
        self.assertTrue(payload["checks"]["protective_orders_ready"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["would_place_order"])

    def test_protective_orders_required_but_not_enabled_blocks(self) -> None:
        signal_id = self._seed_ready_candidate()
        evaluate_live_approval_request(text=f"LIVE APPROVE {signal_id}", log_dir=self.log_dir)
        env = self._live_env(kill_switch=False, protective_enabled=False)

        payload = build_live_begins_status(log_dir=self.log_dir, env=env)

        self.assertEqual("BLOCKED", payload["status"])
        self.assertFalse(payload["checks"]["protective_orders_ready"])
        self.assertIn("protective orders are required but not ready/enabled", payload["blockers"])
        self.assertFalse(payload["real_order_placed"])

    def test_secret_hygiene(self) -> None:
        self._seed_ready_candidate()
        env = self._live_env(kill_switch=False, protective_enabled=True)
        env["TELEGRAM_BOT_TOKEN"] = "secret-telegram-token"
        env["BINANCE_API_KEY"] = "secret-binance-key"
        env["BINANCE_API_SECRET"] = "secret-binance-secret"

        payload = build_live_begins_status(log_dir=self.log_dir, env=env)
        rendered = str(payload)

        self.assertFalse(payload["secrets_shown"])
        self.assertNotIn("secret-telegram-token", rendered)
        self.assertNotIn("secret-binance-key", rendered)
        self.assertNotIn("secret-binance-secret", rendered)
        self.assertNotIn("raw env", rendered.lower())

    def test_api_endpoints_return_json_and_record_check_event(self) -> None:
        status_response = self.client.get("/live/begins/status")
        check_response = self.client.post("/live/begins/check", json={})
        events = load_live_begins_events(limit=10, log_dir=self.log_dir)

        self.assertEqual(200, status_response.status_code)
        self.assertEqual(200, check_response.status_code)
        self.assertIn(status_response.json()["status"], {"BLOCKED", "NOT_READY"})
        self.assertFalse(status_response.json()["order_placed"])
        self.assertFalse(check_response.json()["real_order_placed"])
        self.assertEqual(1, len(events))
        self.assertEqual("live_begins_check", events[0]["event_type"])
        self.assertFalse(events[0]["secrets_shown"])

    def test_telegram_live_begins_and_blocked_live_commands_are_safe(self) -> None:
        live_begins = handle_telegram_operator_command(text="LIVE BEGINS", log_dir=self.log_dir)
        raw_yes = handle_telegram_operator_command(text="YES", log_dir=self.log_dir)
        trade_now = handle_telegram_operator_command(text="trade now live", log_dir=self.log_dir)

        self.assertEqual("ACCEPTED", live_begins["result_status"])
        self.assertEqual("live_begins", live_begins["normalized_action"])
        self.assertIn("R50 live-begins gate", live_begins["message"])
        self.assertIn("No order placed", live_begins["message"])
        self.assertEqual("REJECTED", raw_yes["result_status"])
        self.assertEqual("BLOCKED", trade_now["result_status"])
        self.assertFalse(raw_yes["order_placed"])
        self.assertFalse(trade_now["real_order_placed"])

    def test_check_does_not_call_binance_network(self) -> None:
        with patch("urllib.request.urlopen", side_effect=AssertionError("network should not be called")):
            payload = evaluate_and_record_live_begins(log_dir=self.log_dir, env=self._live_env())

        self.assertIn(payload["status"], {"BLOCKED", "NOT_READY"})
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])

    def _seed_ready_candidate(self) -> str:
        self._seed_promoted_strategy(samples=30)
        signal_id = "BTCUSDT|13m|long|2026-05-05T10:00:00+00:00"
        archive.append_signal(self._eligible_signal(signal_id=signal_id), log_dir=self.log_dir)
        return signal_id

    def _seed_promoted_strategy(self, *, samples: int) -> None:
        base_time = datetime.now(UTC) - timedelta(hours=3)
        for index in range(samples):
            timestamp = (base_time + timedelta(minutes=index)).isoformat()
            signal_id = f"BTCUSDT|13m|long|promoted-{index}"
            signal = self._eligible_signal(signal_id=signal_id, timestamp=timestamp)
            outcome = OutcomeRecord(
                signal_id=signal_id,
                symbol="BTCUSDT",
                timeframe="13m",
                direction="long",
                timestamp=timestamp,
                entry_price=100.0,
                exit_price=100.2,
                fill_status="filled",
                outcome="win",
                mae_pct=0.05,
                mfe_pct=0.2,
                pnl_pct=0.2,
                stop_hit=False,
                evaluated_at=(base_time + timedelta(minutes=index + 1)).isoformat(),
                entry_mode="ladder_close_50_618",
            )
            archive.append_signal(signal, log_dir=self.log_dir)
            archive.append_outcome(outcome, log_dir=self.log_dir)

    @staticmethod
    def _live_env(*, kill_switch: bool = True, protective_enabled: bool = False) -> dict[str, str]:
        return {
            "HAMMER_BINANCE_CONNECTOR_MODE": "LIVE_ORDER_ENABLED",
            "HAMMER_BINANCE_LIVE_ENABLED": "true",
            "HAMMER_LIVE_EXECUTION_ENABLED": "true",
            "HAMMER_ALLOW_LIVE_ORDERS": "true",
            "HAMMER_GLOBAL_KILL_SWITCH": "true" if kill_switch else "false",
            "HAMMER_PROTECTIVE_ORDERS_REQUIRED": "true",
            "HAMMER_PROTECTIVE_ORDERS_ENABLED": "true" if protective_enabled else "false",
            "HAMMER_PROTECTIVE_ORDER_MODE": "LIVE_PROTECTIVE_ENABLED" if protective_enabled else "PREVIEW_ONLY",
            "BINANCE_API_KEY": "present-key",
            "BINANCE_API_SECRET": "present-secret",
        }

    @staticmethod
    def _eligible_signal(
        *,
        signal_id: str,
        symbol: str = "BTCUSDT",
        timeframe: str = "13m",
        direction: str = "long",
        tradable: bool = True,
        reject_reason: str | None = None,
        timestamp: str | None = None,
    ) -> SignalRecord:
        return SignalRecord(
            signal_id=signal_id,
            symbol=symbol,
            timeframe=timeframe,
            direction=direction,
            timestamp=timestamp or (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
            hammer_strength=100.0,
            hammer_high=101.0,
            hammer_low=94.0,
            fib_50=100.5,
            fib_618=100.0,
            fib_650=99.5,
            fib_786=98.5,
            invalidation=95.0,
            bias_timeframe="4H",
            bias_direction="bullish",
            bias_aligned=True,
            same_direction_streak=0,
            opposite_direction_streak=0,
            tradable=tradable,
            reject_reason=reject_reason,
            trend_direction="bullish",
            trend_strength_score=0.6,
            trend_lookback_candles=3,
            ema_4h_20=100.0,
            price_vs_ema_4h_pct=0.1,
            signal_close=100.0,
            rsi_value=50.0,
            rsi_state="neutral",
            divergence_type="bullish",
            divergence_confirmed=True,
        )


if __name__ == "__main__":
    unittest.main()
