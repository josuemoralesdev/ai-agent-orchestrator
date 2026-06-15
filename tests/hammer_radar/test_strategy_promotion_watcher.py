from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator import archive
from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.models import OutcomeRecord, SignalRecord
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR
from src.app.hammer_radar.operator.strategy_performance import StrategyAuditConfig
from src.app.hammer_radar.operator.strategy_promotion_watcher import (
    STRATEGY_NEAR_PROMOTION,
    STRATEGY_PROMOTION_READY,
    build_strategy_promotion_status,
    check_strategy_promotions,
    load_strategy_promotion_events,
)


class StrategyPromotionWatcherTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict("os.environ", {LOG_DIR_ENV_VAR: str(self.log_dir)})
        self.env_patch.start()
        self.client = TestClient(app)
        self.config = StrategyAuditConfig(
            min_sample=30,
            min_win_rate=45.0,
            allowed_tiny_live_timeframes=("13m", "44m"),
            paper_only_timeframes=("4m", "8m", "88m"),
            context_only_timeframes=("4H", "13H", "13D", "888m"),
            blocked_timeframes=("22m", "55m", "222m", "444m"),
        )

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_near_promotion_detection_for_13m_ladder_25_of_30(self) -> None:
        self._seed_group("near", "13m", "long", "ladder_close_50_618", wins=17, losses=8)

        payload = build_strategy_promotion_status(log_dir=self.log_dir, config=self.config)

        self.assertEqual(1, len(payload["near_promotion"]))
        row = payload["near_promotion"][0]
        self.assertEqual(STRATEGY_NEAR_PROMOTION, row["event_type"])
        self.assertEqual("BTCUSDT|13m|long|ladder_close_50_618", row["strategy_key"])
        self.assertEqual(25, row["sample_count"])
        self.assertEqual(30, row["required_sample_count"])
        self.assertFalse(row["live_execution_enabled"])
        self.assertFalse(row["allow_live_orders"])
        self.assertTrue(row["global_kill_switch"])
        self.assertFalse(row["order_placed"])
        self.assertFalse(row["execution_attempted"])
        self.assertFalse(row["order_payload_created"])

    def test_promotion_ready_detection_when_sample_count_reaches_30(self) -> None:
        self._seed_group("ready", "13m", "long", "ladder_close_50_618", wins=20, losses=10)

        payload = build_strategy_promotion_status(log_dir=self.log_dir, config=self.config)

        self.assertEqual(55.0, payload["config"]["min_win_rate"])
        self.assertEqual(55.0, payload["config"]["min_win_rate_pct"])
        self.assertEqual(55.0, payload["config"]["tiny_live_min_win_rate_pct"])
        self.assertEqual(45.0, payload["config"]["legacy_min_win_rate_pct"])
        self.assertTrue(payload["config"]["evidence_policy_all_timeframes_enabled"])
        self.assertEqual(1, len(payload["promotion_ready"]))
        row = payload["promotion_ready"][0]
        self.assertEqual(STRATEGY_PROMOTION_READY, row["event_type"])
        self.assertEqual(30, row["sample_count"])
        self.assertEqual("BTCUSDT|13m|long|ladder_close_50_618", row["strategy_key"])

    def test_13m_47_27_win_rate_is_not_promotion_ready(self) -> None:
        self._seed_group("weak13", "13m", "long", "ladder_close_50_618", wins=26, losses=29)

        payload = build_strategy_promotion_status(log_dir=self.log_dir, config=self.config)

        self.assertEqual([], payload["promotion_ready"])
        blocked = payload["blocked_candidates"]
        self.assertEqual(1, len(blocked))
        self.assertEqual("BTCUSDT|13m|long|ladder_close_50_618", blocked[0]["strategy_key"])
        self.assertEqual(47.27, blocked[0]["win_rate_pct"])
        self.assertIn("win_rate_below_operator_55_policy", blocked[0]["blockers"])
        self.assertIn("below_operator_55_policy", blocked[0]["blockers"])
        self.assertNotEqual("ELIGIBLE_FOR_FUTURE_TINY_LIVE", blocked[0]["recommendation"])

    def test_44m_58_57_win_rate_is_promotion_ready(self) -> None:
        self._seed_group("ready44", "44m", "long", "ladder_close_50_618", wins=41, losses=29)

        payload = build_strategy_promotion_status(log_dir=self.log_dir, config=self.config)

        self.assertEqual(1, len(payload["promotion_ready"]))
        row = payload["promotion_ready"][0]
        self.assertEqual("BTCUSDT|44m|long|ladder_close_50_618", row["strategy_key"])
        self.assertEqual(58.57, row["win_rate_pct"])
        self.assertEqual(1, len(payload["live_qualified_lanes"]))
        self.assertEqual("LIVE_QUALIFIED", payload["live_qualified_lanes"][0]["watch_category"])
        self.assertTrue(payload["live_qualified_lanes"][0]["manual_live_unlock_available"])

    def test_near_miss_incubator_is_watchlist_only(self) -> None:
        self._seed_group("near-miss", "8m", "short", "ladder_close_50_618", wins=16, losses=14)

        payload = build_strategy_promotion_status(log_dir=self.log_dir, config=self.config)

        self.assertEqual([], payload["promotion_ready"])
        self.assertEqual(1, len(payload["near_miss_incubator_lanes"]))
        row = payload["near_miss_incubator_lanes"][0]
        self.assertEqual("BTCUSDT|8m|short|ladder_close_50_618", row["strategy_key"])
        self.assertEqual("NEAR_MISS_INCUBATOR", row["watch_category"])
        self.assertFalse(row["manual_live_unlock_available"])
        self.assertFalse(row["final_command_available"])
        self.assertIn("strategy_near_miss_not_live_eligible", row["blockers"])
        self.assertFalse(payload["qualified_candidate_watch"]["near_miss_manual_unlock_available"])
        self.assertEqual("WAIT", payload["qualified_candidate_watch"]["next_action"])

    def test_below_53_is_paper_only(self) -> None:
        self._seed_group("paper", "8m", "short", "ladder_close_50_618", wins=15, losses=15)

        payload = build_strategy_promotion_status(log_dir=self.log_dir, config=self.config)

        self.assertEqual(1, len(payload["paper_only_lanes"]))
        row = payload["paper_only_lanes"][0]
        self.assertEqual("PAPER_ONLY", row["watch_category"])
        self.assertFalse(row["manual_live_unlock_available"])

    def test_promotion_for_shorts_when_evidence_passes(self) -> None:
        self._seed_group("short", "13m", "short", "ladder_close_50_618", wins=25, losses=5)

        payload = build_strategy_promotion_status(log_dir=self.log_dir, config=self.config)

        self.assertEqual([], payload["near_promotion"])
        self.assertEqual(1, len(payload["promotion_ready"]))

    def test_paper_only_timeframes_can_promote_when_evidence_passes(self) -> None:
        self._seed_group("four", "4m", "long", "ladder_close_50_618", wins=25, losses=5)
        self._seed_group("eight", "8m", "long", "ladder_close_50_618", wins=25, losses=5)

        payload = build_strategy_promotion_status(log_dir=self.log_dir, config=self.config)

        self.assertEqual([], payload["near_promotion"])
        self.assertEqual(2, len(payload["promotion_ready"]))

    def test_context_only_timeframes_can_promote_when_evidence_passes(self) -> None:
        self._seed_group("context", "4H", "long", "ladder_close_50_618", wins=25, losses=5)

        payload = build_strategy_promotion_status(log_dir=self.log_dir, config=self.config)

        self.assertEqual([], payload["near_promotion"])
        self.assertEqual(1, len(payload["promotion_ready"]))

    def test_blocked_timeframes_can_promote_when_evidence_passes(self) -> None:
        self._seed_group("blocked", "55m", "long", "ladder_close_50_618", wins=25, losses=5)

        payload = build_strategy_promotion_status(log_dir=self.log_dir, config=self.config)

        self.assertEqual([], payload["near_promotion"])
        self.assertEqual(1, len(payload["promotion_ready"]))

    def test_promotion_events_are_persisted_and_deduped(self) -> None:
        self._seed_group("ready", "13m", "long", "ladder_close_50_618", wins=20, losses=10)

        first = check_strategy_promotions(log_dir=self.log_dir, config=self.config)
        second = check_strategy_promotions(log_dir=self.log_dir, config=self.config)
        records = load_strategy_promotion_events(limit=10, log_dir=self.log_dir)

        self.assertTrue(first["recorded"])
        self.assertEqual(1, len(first["recorded_events"]))
        self.assertFalse(second["recorded"])
        self.assertEqual(1, len(second["skipped_events"]))
        self.assertEqual("STRATEGY_PROMOTION_ALREADY_RECORDED", second["skipped_events"][0]["event_type"])
        self.assertEqual(1, len(records))
        self.assertTrue((self.log_dir / "strategy_promotion_events.ndjson").exists())

    def test_api_status_returns_safety_flags(self) -> None:
        response = self.client.get("/strategy-promotion/status")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertFalse(payload["live_execution_enabled"])
        self.assertFalse(payload["allow_live_orders"])
        self.assertTrue(payload["global_kill_switch"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["execution_attempted"])
        self.assertFalse(payload["order_payload_created"])
        self.assertFalse(payload["secrets_shown"])

    def test_api_check_records_events_and_events_endpoint_lists_records(self) -> None:
        self._seed_group("near", "13m", "long", "ladder_close_50_618", wins=17, losses=8)

        check_response = self.client.post("/strategy-promotion/check", json={})
        events_response = self.client.get("/strategy-promotion/events")
        event_id = check_response.json()["recorded_events"][0]["event_id"]
        single_response = self.client.get(f"/strategy-promotion/events/{event_id}")

        self.assertEqual(200, check_response.status_code)
        self.assertTrue(check_response.json()["recorded"])
        self.assertFalse(check_response.json()["order_placed"])
        self.assertEqual(200, events_response.status_code)
        self.assertEqual(1, len(events_response.json()["strategy_promotion_events"]))
        self.assertEqual(200, single_response.status_code)
        self.assertEqual(event_id, single_response.json()["event_id"])

    def test_message_wording_is_review_only_and_no_live_orders(self) -> None:
        self._seed_group("near", "13m", "long", "ladder_close_50_618", wins=17, losses=8)

        payload = check_strategy_promotions(log_dir=self.log_dir, config=self.config)
        message = payload["message_payloads"][0]["message"]

        self.assertIn("Future tiny-live review candidate.", message)
        self.assertIn("Recommendation only, not permission to execute.", message)
        self.assertIn("Exact LIVE APPROVE <signal_id> and all live safety gates are still required.", message)
        self.assertIn("Execution remains disabled.", message)
        self.assertIn("No live orders.", message)
        self.assertFalse(payload["message_payloads"][0]["secrets_shown"])

    def test_no_signed_order_payload_is_created(self) -> None:
        self._seed_group("ready", "13m", "long", "ladder_close_50_618", wins=20, losses=10)

        payload = check_strategy_promotions(log_dir=self.log_dir, config=self.config)

        self.assertFalse(payload["order_payload_created"])
        self.assertFalse(payload["recorded_events"][0]["order_payload_created"])

    def _seed_group(
        self,
        prefix: str,
        timeframe: str,
        direction: str,
        entry_mode: str,
        *,
        wins: int,
        losses: int,
    ) -> None:
        pnl_values = [0.2] * wins + [-0.1] * losses
        base_time = datetime.now(UTC) - timedelta(hours=1)
        for index, pnl_pct in enumerate(pnl_values):
            timestamp = (base_time + timedelta(minutes=index)).isoformat()
            signal_id = f"BTCUSDT|{timeframe}|{direction}|{prefix}-{index}"
            signal = SignalRecord(
                signal_id=signal_id,
                symbol="BTCUSDT",
                timeframe=timeframe,
                direction=direction,
                timestamp=timestamp,
                hammer_strength=100.0,
                hammer_high=101.0,
                hammer_low=94.0,
                fib_50=100.5,
                fib_618=100.0,
                fib_650=99.5,
                fib_786=98.5,
                invalidation=95.0,
                bias_timeframe="4H",
                bias_direction="bullish" if direction == "long" else "bearish",
                bias_aligned=True,
                same_direction_streak=0,
                opposite_direction_streak=0,
                tradable=True,
                trend_direction="bullish" if direction == "long" else "bearish",
                trend_strength_score=0.6,
            )
            outcome = OutcomeRecord(
                signal_id=signal_id,
                symbol="BTCUSDT",
                timeframe=timeframe,
                direction=direction,
                timestamp=timestamp,
                entry_price=100.0,
                exit_price=100.0 + pnl_pct,
                fill_status="filled",
                outcome="win" if pnl_pct > 0 else "loss",
                mae_pct=abs(pnl_pct) / 2.0,
                mfe_pct=abs(pnl_pct),
                pnl_pct=pnl_pct,
                stop_hit=pnl_pct <= 0,
                evaluated_at=(base_time + timedelta(minutes=index + 1)).isoformat(),
                entry_mode=entry_mode,
            )
            archive.append_signal(signal, log_dir=self.log_dir)
            archive.append_outcome(outcome, log_dir=self.log_dir)


if __name__ == "__main__":
    unittest.main()
