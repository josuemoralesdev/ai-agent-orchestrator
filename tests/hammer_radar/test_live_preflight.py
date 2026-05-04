from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator import archive
from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.live_preflight import (
    NO_PROMOTED_STRATEGY,
    PREFLIGHT_BLOCKED,
    PREFLIGHT_READY_BUT_EXECUTION_DISABLED,
    WAITING_FOR_FRESH_PROMOTED_SIGNAL,
    build_promoted_strategy_preflight,
    evaluate_and_record_live_preflight,
    load_live_preflight_packs,
)
from src.app.hammer_radar.operator.models import OutcomeRecord, SignalRecord
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR
from src.app.hammer_radar.operator.strategy_performance import StrategyAuditConfig


class LivePreflightTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict("os.environ", {LOG_DIR_ENV_VAR: str(self.log_dir)})
        self.env_patch.start()
        self.client = TestClient(app)
        self.config = StrategyAuditConfig(
            min_sample=3,
            min_win_rate=45.0,
            allowed_tiny_live_timeframes=("13m", "44m"),
            paper_only_timeframes=("4m", "8m", "88m"),
            context_only_timeframes=("4H", "13H", "13D", "888m"),
            blocked_timeframes=("22m", "55m", "222m", "444m"),
        )

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_no_promoted_strategy_returns_no_promoted_strategy(self) -> None:
        payload = build_promoted_strategy_preflight(log_dir=self.log_dir, config=self.config)

        self.assertEqual(NO_PROMOTED_STRATEGY, payload["preflight_status"])
        self.assertFalse(payload["promoted_strategy_ready"])
        self.assertFalse(payload["matching_fresh_signal_found"])
        self.assertFalse(payload["live_execution_enabled"])
        self.assertFalse(payload["order_placed"])

    def test_promoted_strategy_without_fresh_signal_waits(self) -> None:
        self._seed_promoted_strategy(samples=3)

        payload = build_promoted_strategy_preflight(log_dir=self.log_dir, config=self.config)

        self.assertEqual(WAITING_FOR_FRESH_PROMOTED_SIGNAL, payload["preflight_status"])
        self.assertTrue(payload["promoted_strategy_ready"])
        self.assertFalse(payload["matching_fresh_signal_found"])
        self.assertIn("no fresh BTCUSDT 13m long signal matching promoted strategy", payload["blockers"])
        self.assertEqual("Wait for fresh promoted signal; do not approve live now.", payload["operator_next_action"])
        self.assertIsNone(payload["required_exact_command"])

    def test_promoted_strategy_with_fresh_matching_signal_builds_preflight_pack(self) -> None:
        self._seed_promoted_strategy(samples=3)
        signal = self._eligible_signal(signal_id="BTCUSDT|13m|long|fresh-match")
        archive.append_signal(signal, log_dir=self.log_dir)

        payload = build_promoted_strategy_preflight(log_dir=self.log_dir, config=self.config)

        self.assertIn(
            payload["preflight_status"],
            {PREFLIGHT_BLOCKED, PREFLIGHT_READY_BUT_EXECUTION_DISABLED},
        )
        self.assertTrue(payload["promoted_strategy_ready"])
        self.assertTrue(payload["matching_fresh_signal_found"])
        self.assertEqual(signal.signal_id, payload["candidate_signal_id"])
        self.assertEqual(f"LIVE APPROVE {signal.signal_id}", payload["required_exact_command"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["execution_attempted"])
        self.assertFalse(payload["order_payload_created"])

    def test_wrong_timeframe_short_eth_expired_and_rejected_candidates_do_not_match(self) -> None:
        cases = [
            self._eligible_signal(signal_id="wrong-timeframe", timeframe="44m"),
            self._eligible_signal(signal_id="short-signal", direction="short", divergence_type="bearish"),
            self._eligible_signal(signal_id="eth-signal", symbol="ETHUSDT"),
            self._eligible_signal(
                signal_id="expired-signal",
                timestamp=(datetime.now(UTC) - timedelta(hours=2)).isoformat(),
            ),
            self._eligible_signal(signal_id="rejected-signal", tradable=False, reject_reason="bias_not_aligned"),
        ]
        for signal in cases:
            with self.subTest(signal_id=signal.signal_id):
                with tempfile.TemporaryDirectory() as temp_name:
                    log_dir = Path(temp_name)
                    self._seed_promoted_strategy(samples=3, log_dir=log_dir)
                    archive.append_signal(signal, log_dir=log_dir)

                    payload = build_promoted_strategy_preflight(log_dir=log_dir, config=self.config)

                    self.assertEqual(WAITING_FOR_FRESH_PROMOTED_SIGNAL, payload["preflight_status"])
                    self.assertFalse(payload["matching_fresh_signal_found"])

    def test_exact_command_is_included_only_when_signal_exists(self) -> None:
        self._seed_promoted_strategy(samples=3)
        waiting = build_promoted_strategy_preflight(log_dir=self.log_dir, config=self.config)
        signal = self._eligible_signal(signal_id="BTCUSDT|13m|long|command")
        archive.append_signal(signal, log_dir=self.log_dir)
        found = build_promoted_strategy_preflight(log_dir=self.log_dir, config=self.config)

        self.assertIsNone(waiting["required_exact_command"])
        self.assertEqual(f"LIVE APPROVE {signal.signal_id}", found["required_exact_command"])

    def test_preflight_packs_are_persisted_and_duplicate_waiting_state_is_deduped(self) -> None:
        self._seed_promoted_strategy(samples=3)

        first = evaluate_and_record_live_preflight(log_dir=self.log_dir, config=self.config)
        second = evaluate_and_record_live_preflight(log_dir=self.log_dir, config=self.config)
        records = load_live_preflight_packs(limit=10, log_dir=self.log_dir)

        self.assertTrue(first["recorded"])
        self.assertFalse(first["deduped"])
        self.assertFalse(second["recorded"])
        self.assertTrue(second["deduped"])
        self.assertEqual(1, len(records))
        self.assertTrue((self.log_dir / "live_preflight_packs.ndjson").exists())

    def test_new_signal_id_records_new_pack(self) -> None:
        self._seed_promoted_strategy(samples=3)
        evaluate_and_record_live_preflight(log_dir=self.log_dir, config=self.config)
        archive.append_signal(self._eligible_signal(signal_id="BTCUSDT|13m|long|new-pack"), log_dir=self.log_dir)

        second = evaluate_and_record_live_preflight(log_dir=self.log_dir, config=self.config)
        records = load_live_preflight_packs(limit=10, log_dir=self.log_dir)

        self.assertTrue(second["recorded"])
        self.assertFalse(second["deduped"])
        self.assertEqual(2, len(records))

    def test_api_endpoints_return_safety_flags_and_records(self) -> None:
        self._seed_promoted_strategy(samples=30)

        status_response = self.client.get("/live-preflight/promoted-strategy")
        check_response = self.client.post("/live-preflight/evaluate", json={})
        packs_response = self.client.get("/live-preflight/packs")
        preflight_id = check_response.json()["preflight_pack"]["preflight_id"]
        single_response = self.client.get(f"/live-preflight/packs/{preflight_id}")

        self.assertEqual(200, status_response.status_code)
        self.assertFalse(status_response.json()["live_execution_enabled"])
        self.assertFalse(status_response.json()["allow_live_orders"])
        self.assertTrue(status_response.json()["global_kill_switch"])
        self.assertFalse(status_response.json()["order_placed"])
        self.assertFalse(status_response.json()["execution_attempted"])
        self.assertFalse(status_response.json()["order_payload_created"])
        self.assertFalse(status_response.json()["secrets_shown"])
        self.assertEqual(200, check_response.status_code)
        self.assertTrue(check_response.json()["recorded"])
        self.assertEqual(200, packs_response.status_code)
        self.assertEqual(1, len(packs_response.json()["live_preflight_packs"]))
        self.assertEqual(200, single_response.status_code)
        self.assertEqual(preflight_id, single_response.json()["preflight_id"])

    def test_operator_latest_includes_latest_live_preflight_pack(self) -> None:
        self._seed_promoted_strategy(samples=30)
        record = self.client.post("/live-preflight/evaluate", json={}).json()["preflight_pack"]

        latest_response = self.client.get("/operator/latest")

        self.assertEqual(200, latest_response.status_code)
        latest = latest_response.json()["latest_live_preflight_pack"]
        self.assertEqual(record["preflight_id"], latest["preflight_id"])

    def test_message_wording_and_no_signed_payload(self) -> None:
        self._seed_promoted_strategy(samples=3)
        payload = evaluate_and_record_live_preflight(log_dir=self.log_dir, config=self.config)
        message = payload["message_payloads"][0]["message"]

        self.assertIn("Recommendation/preflight only, not permission to execute.", message)
        self.assertIn("No live orders.", message)
        self.assertIn("No signed payloads.", message)
        self.assertIn("Execution remains disabled.", message)
        self.assertFalse(payload["order_payload_created"])
        self.assertFalse(payload["preflight_pack"]["order_payload_created"])

    def _seed_promoted_strategy(self, *, samples: int, log_dir: Path | None = None) -> None:
        target_log_dir = log_dir or self.log_dir
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
            archive.append_signal(signal, log_dir=target_log_dir)
            archive.append_outcome(outcome, log_dir=target_log_dir)

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
        rsi_state: str = "neutral",
        bias_direction: str = "bullish",
        bias_aligned: bool = True,
        trend_direction: str | None = "bullish",
        divergence_type: str | None = "bullish",
        divergence_confirmed: bool = True,
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
            bias_direction=bias_direction,
            bias_aligned=bias_aligned,
            same_direction_streak=0,
            opposite_direction_streak=0,
            tradable=tradable,
            reject_reason=reject_reason,
            trend_direction=trend_direction,
            trend_strength_score=0.6,
            trend_lookback_candles=3,
            ema_4h_20=100.0,
            price_vs_ema_4h_pct=0.1,
            signal_close=100.0,
            rsi_value=50.0,
            rsi_state=rsi_state,
            divergence_type=divergence_type,
            divergence_confirmed=divergence_confirmed,
        )


if __name__ == "__main__":
    unittest.main()
