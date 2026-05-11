from __future__ import annotations

import tempfile
import unittest
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.archive import append_signal
from src.app.hammer_radar.operator.first_live_chain_runbook import build_first_live_chain_status, read_recent_ndjson_records
from src.app.hammer_radar.operator.live_approval import append_live_approval_request
from src.app.hammer_radar.operator.live_execution_intent import append_live_execution_intent
from src.app.hammer_radar.operator.live_executor_rehearsal import append_live_executor_rehearsal
from src.app.hammer_radar.operator.models import SignalRecord
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR
from src.app.hammer_radar.operator.telegram_operator_bridge import handle_telegram_operator_command


class FirstLiveChainRunbookTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict("os.environ", {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False)
        self.env_patch.start()
        self.client = TestClient(app)
        timestamp = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
        self.signal_id = f"BTCUSDT|13m|long|{timestamp}"
        self.intent_id = "intent-r65"
        self.rehearsal_id = "rehearsal-r65"

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_default_status_safe(self) -> None:
        payload = self.client.get("/live/first-chain/status").json()

        self.assertEqual("R65", payload["phase"])
        self.assertEqual("fast", payload["performance"]["mode"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["network_allowed"])
        self.assertFalse(payload["secrets_shown"])

    def test_default_waits_or_blocks_safely(self) -> None:
        payload = build_first_live_chain_status(log_dir=self.log_dir, env={})

        self.assertFalse(payload["chain_state"]["exact_chain_resolved"])
        self.assertIn(payload["next_action"]["kind"], {"wait_for_signal", "blocked"})
        self.assertNotEqual(True, payload.get("live_eligibility"))

    def test_phase_statuses_surface_r58_to_r64(self) -> None:
        payload = build_first_live_chain_status(log_dir=self.log_dir, env={})
        statuses = payload["phase_statuses"]

        for key in (
            "r58_profile",
            "r59_readiness",
            "r60_caps",
            "r61_adapter",
            "r62_ladder",
            "r63_protective",
            "r64_test_order_gate",
        ):
            self.assertIn(key, statuses)

    def test_operator_sequence_present(self) -> None:
        payload = build_first_live_chain_status(log_dir=self.log_dir, env={})
        sequence = payload["operator_sequence"]

        self.assertGreaterEqual(len(sequence), 8)
        self.assertEqual([1, 2, 3], [item["step"] for item in sequence[:3]])
        self.assertTrue(all(item["required"] for item in sequence))
        self.assertFalse(payload["execution_attempted"])

    def test_no_fresh_signal_waits(self) -> None:
        payload = build_first_live_chain_status(log_dir=self.log_dir, env={})

        self.assertIn(payload["status"], {"WAITING_FOR_FRESH_SIGNAL", "BLOCKED"})
        self.assertIn(payload["next_action"]["kind"], {"wait_for_signal", "blocked"})

    def test_fresh_signal_without_approval_waits_for_approval(self) -> None:
        self._append_signal()
        with self._patched_heavy_builders_raise():
            payload = build_first_live_chain_status(log_dir=self.log_dir, env={})

        self.assertEqual("WAITING_FOR_APPROVAL", payload["status"])
        self.assertTrue(payload["current_signal"]["first_live_fresh"])
        self.assertEqual(13.5, payload["current_signal"]["freshness_cutoff_minutes"])
        self.assertEqual("strict_first_live", payload["current_signal"]["freshness_policy"])
        self.assertEqual("approve_signal", payload["next_action"]["kind"])
        self.assertEqual(f"LIVE APPROVE {self.signal_id}", payload["next_action"]["telegram_command"])
        self.assertTrue(payload["performance"]["heavy_builders_skipped"])

    def test_approve_signal_api_hint_uses_real_operator_route(self) -> None:
        self._append_signal()
        payload = build_first_live_chain_status(log_dir=self.log_dir, env={})

        self.assertEqual("approve_signal", payload["next_action"]["kind"])
        self.assertIn("/operator/live-approval/evaluate", payload["next_action"]["api_command"])
        self.assertNotIn("POST /live-approval/evaluate", payload["next_action"]["api_command"])
        approve_step = payload["operator_sequence"][1]
        self.assertEqual("POST /operator/live-approval/evaluate", approve_step["api_hint"])

    def test_stale_13m_signal_blocked_by_strict_first_live_cutoff(self) -> None:
        self._append_signal(timeframe="13m", age_minutes=20.17, freshness_status="fresh")
        with self._patched_heavy_builders_raise():
            payload = build_first_live_chain_status(log_dir=self.log_dir, env={})

        self.assertEqual("WAITING_FOR_FRESH_SIGNAL", payload["status"])
        self.assertFalse(payload["current_signal"]["fresh"])
        self.assertTrue(payload["current_signal"]["raw_fresh"])
        self.assertFalse(payload["current_signal"]["first_live_fresh"])
        self.assertEqual(13.5, payload["current_signal"]["freshness_cutoff_minutes"])
        self.assertEqual("wait_for_signal", payload["next_action"]["kind"])
        self.assertEqual("FIRST LIVE CHAIN", payload["next_action"]["telegram_command"])
        self.assertNotIn("LIVE APPROVE", str(payload["next_action"]))

    def test_4m_strict_cutoff(self) -> None:
        self._append_signal(timeframe="4m", age_minutes=4.0)
        allowed = build_first_live_chain_status(log_dir=self.log_dir, env={})

        self._append_signal(timeframe="4m", age_minutes=5.0)
        blocked = build_first_live_chain_status(log_dir=self.log_dir, env={})

        self.assertTrue(allowed["current_signal"]["first_live_fresh"])
        self.assertEqual("WAITING_FOR_FRESH_SIGNAL", allowed["status"])
        self.assertEqual("PAPER_ONLY", allowed["current_signal"]["policy_status"])
        self.assertNotIn("LIVE APPROVE", str(allowed["next_action"]))
        self.assertEqual(4.5, allowed["current_signal"]["freshness_cutoff_minutes"])
        self.assertFalse(blocked["current_signal"]["first_live_fresh"])
        self.assertEqual("WAITING_FOR_FRESH_SIGNAL", blocked["status"])
        self.assertEqual("FIRST LIVE CHAIN", blocked["next_action"]["telegram_command"])

    def test_8m_strict_cutoff(self) -> None:
        self._append_signal(timeframe="8m", age_minutes=8.0)
        allowed = build_first_live_chain_status(log_dir=self.log_dir, env={})

        self._append_signal(timeframe="8m", age_minutes=9.0)
        blocked = build_first_live_chain_status(log_dir=self.log_dir, env={})

        self.assertTrue(allowed["current_signal"]["first_live_fresh"])
        self.assertEqual("WAITING_FOR_FRESH_SIGNAL", allowed["status"])
        self.assertEqual("PAPER_ONLY", allowed["current_signal"]["policy_status"])
        self.assertNotIn("LIVE APPROVE", str(allowed["next_action"]))
        self.assertEqual(8.5, allowed["current_signal"]["freshness_cutoff_minutes"])
        self.assertFalse(blocked["current_signal"]["first_live_fresh"])
        self.assertEqual("WAITING_FOR_FRESH_SIGNAL", blocked["status"])
        self.assertEqual("FIRST LIVE CHAIN", blocked["next_action"]["telegram_command"])

    def test_22m_signal_blocked_by_default(self) -> None:
        self._append_signal(timeframe="22m", age_minutes=5.0, freshness_status="fresh")
        payload = build_first_live_chain_status(log_dir=self.log_dir, env={})

        self.assertEqual("WAITING_FOR_FRESH_SIGNAL", payload["status"])
        self.assertFalse(payload["current_signal"]["first_live_fresh"])
        self.assertIsNone(payload["current_signal"]["freshness_cutoff_minutes"])
        self.assertEqual("FIRST LIVE CHAIN", payload["next_action"]["telegram_command"])

    def test_source_freshness_label_ignored_when_strict_age_exceeds_cutoff(self) -> None:
        self._append_signal(timeframe="13m", age_minutes=20.17, freshness_status="fresh")
        payload = build_first_live_chain_status(log_dir=self.log_dir, env={})

        self.assertTrue(payload["current_signal"]["raw_fresh"])
        self.assertFalse(payload["current_signal"]["first_live_fresh"])
        self.assertFalse(payload["current_signal"]["fresh"])
        self.assertEqual("wait_for_signal", payload["next_action"]["kind"])
        self.assertNotIn("LIVE APPROVE", str(payload["next_action"]))

    def test_approval_without_intent_waits_for_intent(self) -> None:
        self._append_signal()
        self._append_approval()
        with self._patched_heavy_builders_raise():
            payload = build_first_live_chain_status(log_dir=self.log_dir, env={})

        self.assertEqual("WAITING_FOR_INTENT", payload["status"])
        self.assertEqual("create_intent", payload["next_action"]["kind"])
        self.assertEqual(f"LIVE INTENT {self.signal_id}", payload["next_action"]["telegram_command"])

    def test_chain_advances_after_telegram_live_approve(self) -> None:
        self._append_signal()
        before = build_first_live_chain_status(log_dir=self.log_dir, env={})

        approval = handle_telegram_operator_command(text=f"LIVE APPROVE {self.signal_id}", log_dir=self.log_dir)
        after = build_first_live_chain_status(log_dir=self.log_dir, env={})

        self.assertEqual("approve_signal", before["next_action"]["kind"])
        self.assertEqual("ACCEPTED", approval["result_status"])
        self.assertEqual("live_approve", approval["normalized_action"])
        self.assertFalse(approval["order_placed"])
        self.assertFalse(approval["real_order_placed"])
        self.assertFalse(approval["secrets_shown"])
        self.assertTrue(after["chain_state"]["approval_found"])
        self.assertEqual("WAITING_FOR_INTENT", after["status"])
        self.assertEqual("create_intent", after["next_action"]["kind"])
        self.assertEqual(f"LIVE INTENT {self.signal_id}", after["next_action"]["telegram_command"])

    def test_chain_advances_after_telegram_live_intent_uses_r68_approval(self) -> None:
        self._append_signal()
        self._append_approval()
        with self._patched_intent_live_begins(), self._patched_intent_preview():
            intent = handle_telegram_operator_command(text=f"LIVE INTENT {self.signal_id}", log_dir=self.log_dir)
        after = build_first_live_chain_status(log_dir=self.log_dir, env={})

        self.assertEqual("ACCEPTED", intent["result_status"])
        self.assertNotEqual("MISSING", intent["payload"]["live_execution_intent"]["approval_status"])
        self.assertNotIn("exact approval is missing", intent["payload"]["live_execution_intent"]["blockers"])
        self.assertNotIn("exact approval for signal_id is missing", intent["payload"]["live_execution_intent"]["blockers"])
        self.assertFalse(intent["order_placed"])
        self.assertFalse(intent["real_order_placed"])
        self.assertTrue(after["chain_state"]["execution_intent_found"])
        self.assertEqual("run_rehearsal", after["next_action"]["kind"])

    def test_direct_live_approval_endpoint_exists_and_is_safe(self) -> None:
        self._append_signal()

        response = self.client.post("/operator/live-approval/evaluate", json={"text": f"LIVE APPROVE {self.signal_id}"})

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("live_approve_exact", payload["normalized_action"])
        self.assertEqual("ACCEPTED", payload["parse_status"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["execution_attempted"])
        self.assertFalse(payload["order_payload_created"])

    def test_intent_without_rehearsal_waits_for_rehearsal(self) -> None:
        self._append_signal()
        self._append_approval()
        self._append_intent()
        with self._patched_heavy_builders_raise():
            payload = build_first_live_chain_status(log_dir=self.log_dir, env={})

        self.assertEqual("WAITING_FOR_REHEARSAL", payload["status"])
        self.assertEqual("run_rehearsal", payload["next_action"]["kind"])
        self.assertEqual(f"LIVE REHEARSAL {self.intent_id}", payload["next_action"]["telegram_command"])

    def test_rehearsal_without_payloads_or_test_order_waits_conservatively(self) -> None:
        self._append_signal()
        self._append_approval()
        self._append_intent()
        self._append_rehearsal()
        r64 = self._r64_payload(payloads_ready=True, test_order_validated=False)
        with self._patched_preview(), self._patched_r64(r64):
            payload = build_first_live_chain_status(log_dir=self.log_dir, env={})

        self.assertEqual("WAITING_FOR_TEST_ORDER", payload["status"])
        self.assertEqual("validate_test_order", payload["next_action"]["kind"])
        self.assertEqual(f"FIRST LIVE TEST ORDER {self.rehearsal_id}", payload["next_action"]["telegram_command"])
        self.assertFalse(payload["performance"]["heavy_builders_skipped"])

    def test_stale_signal_skips_heavy_payload_builders(self) -> None:
        self._append_signal(timeframe="13m", age_minutes=45.0)
        with self._patched_heavy_builders_raise():
            payload = build_first_live_chain_status(log_dir=self.log_dir, env={})

        self.assertEqual("WAITING_FOR_FRESH_SIGNAL", payload["status"])
        self.assertEqual("wait_for_signal", payload["next_action"]["kind"])
        self.assertTrue(payload["performance"]["heavy_builders_skipped"])

    def test_recent_ndjson_records_are_limited(self) -> None:
        path = self.log_dir / "many.ndjson"
        with path.open("w", encoding="utf-8") as handle:
            for index in range(500):
                handle.write(f'{{"index": {index}}}\n')

        records = read_recent_ndjson_records(path, limit=7)

        self.assertEqual(7, len(records))
        self.assertEqual([499, 498, 497], [item["index"] for item in records[:3]])

    def test_status_endpoint_fast_budget(self) -> None:
        payload = self.client.get("/live/first-chain/status").json()

        self.assertEqual("fast", payload["performance"]["mode"])
        self.assertLess(payload["performance"]["duration_ms"], 2000)

    def test_api_endpoints_persist_sanitized_event(self) -> None:
        status = self.client.get("/live/first-chain/status").json()
        check = self.client.post("/live/first-chain/check").json()
        checks = self.client.get("/live/first-chain/checks").json()

        self.assertEqual("R65", status["phase"])
        self.assertEqual("R65", check["phase"])
        self.assertEqual("ACCEPTED", checks["result_status"])
        self.assertGreaterEqual(checks["count"], 1)
        self.assertFalse(checks["checks"][0]["real_order_placed"])

    def test_telegram_commands(self) -> None:
        chain = handle_telegram_operator_command(text="FIRST LIVE CHAIN", log_dir=self.log_dir)
        next_action = handle_telegram_operator_command(text="FIRST LIVE NEXT", log_dir=self.log_dir)
        runbook = handle_telegram_operator_command(text="FIRST LIVE RUNBOOK", log_dir=self.log_dir)
        sequence = handle_telegram_operator_command(text="FIRST LIVE SEQUENCE", log_dir=self.log_dir)
        checks = handle_telegram_operator_command(text="FIRST LIVE CHAIN CHECKS", log_dir=self.log_dir)
        raw_yes = handle_telegram_operator_command(text="YES", log_dir=self.log_dir)
        trade_now = handle_telegram_operator_command(text="trade now live", log_dir=self.log_dir)

        self.assertEqual("ACCEPTED", chain["result_status"])
        self.assertEqual("ACCEPTED", next_action["result_status"])
        self.assertEqual("ACCEPTED", runbook["result_status"])
        self.assertEqual("ACCEPTED", sequence["result_status"])
        self.assertEqual("fast", next_action["performance"]["mode"])
        self.assertEqual("ACCEPTED", checks["result_status"])
        self.assertEqual("REJECTED", raw_yes["result_status"])
        self.assertEqual("BLOCKED", trade_now["result_status"])
        self.assertFalse(trade_now["order_placed"])
        self.assertFalse(trade_now["real_order_placed"])

    def test_telegram_first_live_next_and_chain_do_not_approve_stale_signal(self) -> None:
        self._append_signal(timeframe="13m", age_minutes=20.17, freshness_status="fresh")

        next_action = handle_telegram_operator_command(text="FIRST LIVE NEXT", log_dir=self.log_dir)
        chain = handle_telegram_operator_command(text="FIRST LIVE CHAIN", log_dir=self.log_dir)
        raw_yes = handle_telegram_operator_command(text="YES", log_dir=self.log_dir)
        trade_now = handle_telegram_operator_command(text="trade now live", log_dir=self.log_dir)

        self.assertEqual("ACCEPTED", next_action["result_status"])
        self.assertEqual("wait_for_signal", next_action["next_action"]["kind"])
        self.assertEqual("FIRST LIVE CHAIN", next_action["next_action"]["telegram_command"])
        self.assertNotIn("LIVE APPROVE", next_action["message"])
        self.assertEqual("wait_for_signal", chain["next_action"]["kind"])
        self.assertNotIn("LIVE APPROVE", chain["message"])
        self.assertEqual("REJECTED", raw_yes["result_status"])
        self.assertEqual("BLOCKED", trade_now["result_status"])

    def test_secret_hygiene(self) -> None:
        env = {
            "BINANCE_API_KEY": "secret-binance-key",
            "BINANCE_API_SECRET": "secret-binance-secret",
            "TELEGRAM_BOT_TOKEN": "secret-telegram-token",
        }

        payload = build_first_live_chain_status(log_dir=self.log_dir, env=env)
        rendered = str(payload)

        self.assertFalse(payload["secrets_shown"])
        self.assertNotIn("secret-binance-key", rendered)
        self.assertNotIn("secret-binance-secret", rendered)
        self.assertNotIn("secret-telegram-token", rendered)
        self.assertNotIn("signature", rendered.lower())
        self.assertNotIn("auth", rendered.lower())

    def test_no_binance_network(self) -> None:
        with patch("urllib.request.urlopen", side_effect=AssertionError("network should not be called")):
            payload = build_first_live_chain_status(log_dir=self.log_dir, env={})

        self.assertFalse(payload["network_allowed"])
        self.assertFalse(payload["real_order_placed"])

    def _append_approval(self) -> None:
        append_live_approval_request(
            {
                "request_id": "approval-r65",
                "created_at": datetime.now(UTC).isoformat(),
                "raw_text": f"LIVE APPROVE {self.signal_id}",
                "normalized_action": "live_approve_exact",
                "parse_status": "ACCEPTED",
                "signal_id": self.signal_id,
                "approval_gate_status": "BLOCKED",
                "order_placed": False,
                "execution_attempted": False,
            },
            log_dir=self.log_dir,
        )

    def _append_signal(
        self,
        *,
        timeframe: str = "13m",
        age_minutes: float = 1.0,
        freshness_status: str | None = None,
    ) -> None:
        timestamp = (datetime.now(UTC) - timedelta(minutes=age_minutes)).isoformat()
        self.signal_id = f"BTCUSDT|{timeframe}|long|{timestamp}"
        signal = SignalRecord(
            signal_id=self.signal_id,
            symbol="BTCUSDT",
            timeframe=timeframe,
            direction="long",
            timestamp=timestamp,
            hammer_strength=1.0,
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
        )
        if freshness_status is None:
            append_signal(signal, log_dir=self.log_dir)
            return
        path = self.log_dir / "signals.ndjson"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = signal.to_dict()
        payload["freshness_status"] = freshness_status
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")

    def _append_intent(self) -> None:
        append_live_execution_intent(
            {
                "execution_intent_id": self.intent_id,
                "status": "INTENT_READY",
                "execution_mode": "INTENT_ONLY",
                "signal_id": self.signal_id,
                "preview_hash": "preview-r65",
                "created_at": datetime.now(UTC).isoformat(),
                "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
                "order_placed": False,
                "real_order_placed": False,
                "execution_attempted": False,
                "secrets_shown": False,
            },
            log_dir=self.log_dir,
        )

    def _append_rehearsal(self) -> None:
        append_live_executor_rehearsal(
            {
                "executor_rehearsal_id": self.rehearsal_id,
                "execution_intent_id": self.intent_id,
                "status": "REHEARSAL_READY",
                "execution_mode": "REHEARSAL_ONLY",
                "signal_id": self.signal_id,
                "preview_hash": "preview-r65",
                "created_at": datetime.now(UTC).isoformat(),
                "network_allowed": False,
                "order_placed": False,
                "real_order_placed": False,
                "execution_attempted": False,
                "secrets_shown": False,
            },
            log_dir=self.log_dir,
        )

    def _patched_intent_live_begins(self):
        return patch(
            "src.app.hammer_radar.operator.live_execution_intent.build_live_begins_status",
            return_value={"status": "READY_FOR_OPERATOR_APPROVAL"},
        )

    def _patched_intent_preview(self):
        return patch(
            "src.app.hammer_radar.operator.live_execution_intent.build_live_execution_preview",
            return_value={
                "status": "PREVIEW_READY",
                "phase": "R51",
                "system": "money_printing_machine_hammer_radar",
                "execution_mode": "PREVIEW_ONLY",
                "latest_signal_id": self.signal_id,
                "symbol": "BTCUSDT",
                "timeframe": "13m",
                "direction": "long",
                "entry": 100.0,
                "stop": 95.0,
                "take_profit": 110.0,
                "order_side": "BUY",
                "position_side": "LONG",
                "margin_usdt": 6.0,
                "leverage": 1.0,
                "notional_usdt": 6.0,
                "risk_usdt": 0.3,
                "quantity": 0.06,
                "protective_orders_preview": {
                    "stop_loss": {"trigger_price": 95.0, "side": "SELL", "reduce_only": True},
                    "take_profit": {"trigger_price": 110.0, "side": "SELL", "reduce_only": True},
                    "reduce_only": True,
                    "status": "READY",
                },
                "order_placed": False,
                "real_order_placed": False,
                "secrets_shown": False,
            },
        )

    def _patched_preview(self):
        return patch(
            "src.app.hammer_radar.operator.first_live_chain_runbook.build_live_execution_preview",
            return_value={
                "status": "PREVIEW_READY",
                "latest_signal_id": self.signal_id,
                "symbol": "BTCUSDT",
                "timeframe": "13m",
                "direction": "long",
                "freshness_status": "fresh",
            },
        )

    def _patched_r64(self, payload: dict | None = None):
        return patch(
            "src.app.hammer_radar.operator.first_live_chain_runbook.build_first_live_test_order_status",
            return_value=payload or self._r64_payload(),
        )

    def _patched_heavy_builders_raise(self):
        return patch.multiple(
            "src.app.hammer_radar.operator.first_live_chain_runbook",
            build_first_live_test_order_status=unittest.mock.Mock(side_effect=AssertionError("R64 should be skipped")),
            build_first_live_ladder_submit_status=unittest.mock.Mock(side_effect=AssertionError("R62 should be skipped")),
            build_first_live_protective_status=unittest.mock.Mock(side_effect=AssertionError("R63 should be skipped")),
        )

    def _r64_payload(self, *, payloads_ready: bool = False, test_order_validated: bool = False) -> dict:
        return {
            "status": "PAYLOADS_READY_TEST_ORDER_MISSING" if payloads_ready and not test_order_validated else "EXACT_CHAIN_MISSING",
            "payload_readiness": {
                "entry_payload_ready": payloads_ready,
                "protective_payloads_ready": payloads_ready,
            },
            "test_order_status": {"test_order_validated_for_signal": test_order_validated},
            "live_eligibility": {"eligible_for_manual_env_arming": False},
            "blockers": [] if payloads_ready else ["payloads missing"],
        }


if __name__ == "__main__":
    unittest.main()
