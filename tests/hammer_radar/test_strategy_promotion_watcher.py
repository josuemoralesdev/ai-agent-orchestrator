from __future__ import annotations

import json
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
    WATCH_BLOCKED_BETRAYAL,
    WATCH_BLOCKED_NEAR_MISS,
    WATCH_BLOCKED_PAPER_ONLY,
    WATCH_FOUND,
    WATCH_WAIT,
    STRATEGY_NEAR_PROMOTION,
    STRATEGY_PROMOTION_READY,
    build_live_qualified_fresh_candidate_watch,
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
        self.assertEqual("STRATEGY_LAB_PAPER_REVIEW", row["recommended_next_action"])
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

    def test_current_live_qualified_lanes_exclude_13m_and_keep_8m_short_incubator(self) -> None:
        self._seed_group("weak13", "13m", "long", "ladder_close_50_618", wins=26, losses=29)
        self._seed_group("near8", "8m", "short", "ladder_close_50_618", wins=16, losses=14)
        self._seed_group("ready44l", "44m", "long", "ladder_close_50_618", wins=25, losses=5)
        self._seed_group("ready44s", "44m", "short", "ladder_close_50_618", wins=25, losses=5)
        self._seed_group("ready55l", "55m", "long", "ladder_close_50_618", wins=25, losses=5)

        payload = build_strategy_promotion_status(log_dir=self.log_dir, config=self.config)

        live_keys = {row["strategy_key"] for row in payload["live_qualified_lanes"]}
        near_keys = {row["strategy_key"] for row in payload["near_miss_incubator_lanes"]}
        self.assertEqual(
            {
                "BTCUSDT|44m|long|ladder_close_50_618",
                "BTCUSDT|44m|short|ladder_close_50_618",
                "BTCUSDT|55m|long|ladder_close_50_618",
            },
            live_keys,
        )
        self.assertNotIn("BTCUSDT|13m|long|ladder_close_50_618", live_keys)
        self.assertIn("BTCUSDT|8m|short|ladder_close_50_618", near_keys)
        near = next(
            row
            for row in payload["near_miss_incubator_lanes"]
            if row["strategy_key"] == "BTCUSDT|8m|short|ladder_close_50_618"
        )
        self.assertFalse(near["manual_live_unlock_available"])
        self.assertFalse(near["final_command_available"])
        self.assertIn("strategy_near_miss_not_live_eligible", near["blockers"])
        self.assertEqual("STRATEGY_LAB_PAPER_REVIEW", near["recommended_next_action"])

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

    def test_44m_long_fresh_live_qualified_candidate_creates_alert_packet(self) -> None:
        self._seed_strategy_status_lane(timeframe="44m", direction="long", win_rate_pct=58.57, sample_count=70)
        archive.append_signal(
            self._eligible_signal(signal_id="fresh|44m|long", timeframe="44m", direction="long"),
            log_dir=self.log_dir,
        )

        payload = build_live_qualified_fresh_candidate_watch(log_dir=self.log_dir, config=self.config)

        packet = payload["candidate_alert_packet"]
        self.assertEqual(WATCH_FOUND, packet["status"])
        self.assertEqual("BTCUSDT|44m|long|ladder_close_50_618", packet["current_candidate"]["lane_key"])
        self.assertEqual(58.57, packet["strategy_evidence"]["win_rate_pct"])
        self.assertEqual(70, packet["strategy_evidence"]["sample_count"])
        self.assertEqual("LIVE_QUALIFIED", packet["strategy_evidence"]["live_qualification_class"])
        self.assertEqual("REVIEW_MANUAL_ONLY_UNLOCK_PACKET", packet["operator_packet"]["recommended_action"])
        self.assertFalse(packet["operator_packet"]["final_command_available"])
        self.assertFalse(packet["operator_packet"]["submit_allowed_from_codex"])
        self.assertFalse(packet["order_placed"])
        self.assertFalse(packet["submit_attempted"])
        self.assertFalse(packet["binance_order_endpoint_called"])
        self.assertFalse(packet["binance_test_order_endpoint_called"])
        self.assertFalse(packet["real_order_placed"])
        self.assertFalse(payload["telegram_compatible_payload"]["send_enabled"])
        self.assertFalse(payload["telegram_compatible_payload"]["sent"])
        self.assertIn("LIVE_QUALIFIED_FRESH_CANDIDATE_FOUND", payload["telegram_compatible_payload"]["message"])
        self.assertIn("operator review only; no live order placed.", payload["telegram_compatible_payload"]["message"])

    def test_44m_short_fresh_live_qualified_candidate_creates_alert_packet(self) -> None:
        self._seed_strategy_status_lane(timeframe="44m", direction="short", win_rate_pct=62.0, sample_count=40)
        archive.append_signal(
            self._eligible_signal(signal_id="fresh|44m|short", timeframe="44m", direction="short"),
            log_dir=self.log_dir,
        )

        payload = build_live_qualified_fresh_candidate_watch(log_dir=self.log_dir, config=self.config)

        packet = payload["candidate_alert_packet"]
        self.assertEqual(WATCH_FOUND, packet["status"])
        self.assertEqual("BTCUSDT|44m|short|ladder_close_50_618", packet["current_candidate"]["lane_key"])
        self.assertEqual("short", packet["current_candidate"]["direction"])
        self.assertFalse(packet["final_command_available"])
        self.assertFalse(packet["submit_allowed_from_codex"])

    def test_55m_long_fresh_live_qualified_candidate_creates_alert_packet(self) -> None:
        self._seed_strategy_status_lane(timeframe="55m", direction="long", win_rate_pct=62.0, sample_count=40)
        archive.append_signal(
            self._eligible_signal(signal_id="fresh|55m|long", timeframe="55m", direction="long"),
            log_dir=self.log_dir,
        )

        payload = build_live_qualified_fresh_candidate_watch(log_dir=self.log_dir, config=self.config)

        packet = payload["candidate_alert_packet"]
        self.assertEqual(WATCH_FOUND, packet["status"])
        self.assertEqual("BTCUSDT|55m|long|ladder_close_50_618", packet["current_candidate"]["lane_key"])
        self.assertEqual(62.0, packet["strategy_evidence"]["win_rate_pct"])

    def test_8m_short_near_miss_returns_incubator_only_no_live_alert(self) -> None:
        self._seed_strategy_status_lane(timeframe="8m", direction="short", win_rate_pct=53.33, sample_count=30)
        archive.append_signal(
            self._eligible_signal(signal_id="fresh|8m|short", timeframe="8m", direction="short"),
            log_dir=self.log_dir,
        )

        payload = build_live_qualified_fresh_candidate_watch(log_dir=self.log_dir, config=self.config)

        packet = payload["candidate_alert_packet"]
        self.assertEqual(WATCH_BLOCKED_NEAR_MISS, packet["status"])
        self.assertIn("strategy_near_miss_not_live_eligible", packet["blocked_by"])
        self.assertEqual("STRATEGY_LAB_PAPER_REVIEW", packet["operator_packet"]["recommended_action"])
        self.assertFalse(packet["operator_packet"]["final_command_available"])
        self.assertFalse(packet["order_placed"])

    def test_below_55_13m_and_4m_lanes_do_not_create_live_alert_packet(self) -> None:
        for timeframe in ("13m", "4m"):
            with self.subTest(timeframe=timeframe):
                self.log_dir = Path(self.temp_dir.name) / f"below-{timeframe}"
                self.log_dir.mkdir()
                self._seed_strategy_status_lane(timeframe=timeframe, direction="long", win_rate_pct=47.27, sample_count=55)
                archive.append_signal(
                    self._eligible_signal(signal_id=f"fresh|{timeframe}|long", timeframe=timeframe, direction="long"),
                    log_dir=self.log_dir,
                )

                payload = build_live_qualified_fresh_candidate_watch(log_dir=self.log_dir, config=self.config)

                packet = payload["candidate_alert_packet"]
                self.assertEqual(WATCH_BLOCKED_PAPER_ONLY, packet["status"])
                self.assertEqual("STRATEGY_LAB_PAPER_REVIEW", packet["operator_packet"]["recommended_action"])
                self.assertFalse(packet["operator_packet"]["final_command_available"])

    def test_betrayal_inverse_candidate_blocks(self) -> None:
        self._seed_strategy_status_lane(timeframe="44m", direction="long", win_rate_pct=62.0, sample_count=40)
        archive.append_signal(
            self._eligible_signal(signal_id="betrayal|inverse|fresh", timeframe="44m", direction="long"),
            log_dir=self.log_dir,
        )

        payload = build_live_qualified_fresh_candidate_watch(log_dir=self.log_dir, config=self.config)

        packet = payload["candidate_alert_packet"]
        self.assertEqual(WATCH_BLOCKED_BETRAYAL, packet["status"])
        self.assertIn("betrayal_inverse_candidate_not_live_eligible", packet["blocked_by"])
        self.assertFalse(packet["operator_packet"]["final_command_available"])

    def test_no_current_candidate_returns_wait(self) -> None:
        self._seed_strategy_status_lane(timeframe="44m", direction="long", win_rate_pct=62.0, sample_count=40)

        payload = build_live_qualified_fresh_candidate_watch(log_dir=self.log_dir, config=self.config)

        packet = payload["candidate_alert_packet"]
        self.assertEqual(WATCH_WAIT, packet["status"])
        self.assertEqual("WAIT", packet["operator_packet"]["recommended_action"])
        self.assertFalse(packet["operator_packet"]["final_command_available"])
        self.assertFalse(packet["order_placed"])

    def test_qualified_candidate_watch_endpoint_returns_read_only_packet(self) -> None:
        self._seed_strategy_status_lane(timeframe="44m", direction="long", win_rate_pct=62.0, sample_count=40)
        archive.append_signal(
            self._eligible_signal(signal_id="fresh|endpoint|44m|long", timeframe="44m", direction="long"),
            log_dir=self.log_dir,
        )

        response = self.client.get("/tiny-live/qualified-candidate-watch")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("LIVE_QUALIFIED_FRESH_CANDIDATE_WATCH", payload["event_type"])
        self.assertEqual(WATCH_FOUND, payload["candidate_alert_packet"]["status"])
        self.assertFalse(payload["candidate_alert_packet"]["final_command_available"])
        self.assertFalse(payload["candidate_alert_packet"]["submit_attempted"])
        self.assertFalse(payload["candidate_alert_packet"]["binance_order_endpoint_called"])
        self.assertFalse(payload["telegram_compatible_payload"]["send_enabled"])

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

    @staticmethod
    def _eligible_signal(
        *,
        signal_id: str,
        timeframe: str,
        direction: str,
    ) -> SignalRecord:
        bearish = direction == "short"
        return SignalRecord(
            signal_id=signal_id,
            symbol="BTCUSDT",
            timeframe=timeframe,
            direction=direction,
            timestamp=(datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
            hammer_strength=100.0,
            hammer_high=101.0,
            hammer_low=94.0,
            fib_50=100.5,
            fib_618=100.0,
            fib_650=99.5,
            fib_786=98.5,
            invalidation=105.0 if bearish else 95.0,
            bias_timeframe="4H",
            bias_direction="bearish" if bearish else "bullish",
            bias_aligned=True,
            same_direction_streak=0,
            opposite_direction_streak=0,
            tradable=True,
            trend_direction="bearish" if bearish else "bullish",
            trend_strength_score=0.6,
            rsi_state="overbought" if bearish else "neutral",
            rsi_value=70.0 if bearish else 50.0,
            divergence_type="bearish" if bearish else "bullish",
            divergence_confirmed=True,
        )

    def _seed_strategy_status_lane(
        self,
        *,
        timeframe: str,
        direction: str,
        win_rate_pct: float,
        sample_count: int,
        avg_pnl_pct: float = 0.1,
    ) -> None:
        lane_key = f"BTCUSDT|{timeframe}|{direction}|ladder_close_50_618"
        record = {
            "qualified_candidate_watch": {
                "live_qualified_lanes": [],
                "near_miss_incubator_lanes": [],
                "paper_only_lanes": [],
            }
        }
        row = {
            "strategy_key": lane_key,
            "sample_count": sample_count,
            "required_sample_count": 30,
            "win_rate_pct": win_rate_pct,
            "avg_pnl_pct": avg_pnl_pct,
            "total_pnl_pct": round(avg_pnl_pct * sample_count, 4),
            "entry_mode": "ladder_close_50_618",
            "timeframe": timeframe,
            "direction": direction,
        }
        if sample_count >= 30 and avg_pnl_pct > 0 and win_rate_pct >= 55.0:
            record["qualified_candidate_watch"]["live_qualified_lanes"].append(row)
        elif sample_count >= 30 and avg_pnl_pct > 0 and win_rate_pct >= 53.0:
            record["qualified_candidate_watch"]["near_miss_incubator_lanes"].append(row)
        else:
            record["qualified_candidate_watch"]["paper_only_lanes"].append(row)
        with (self.log_dir / "strategy_promotion_status.ndjson").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


if __name__ == "__main__":
    unittest.main()
