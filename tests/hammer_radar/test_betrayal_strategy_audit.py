from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from subprocess import run
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator import archive
from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.betrayal_inverse_validation import (
    INSUFFICIENT_TRUE_INVERSE_OUTCOMES,
    TRUE_INVERSE_NO_DATA,
    TRUE_INVERSE_REJECTED,
    TRUE_INVERSE_VALIDATED_PRIMARY,
    build_betrayal_inverse_validation,
)
from src.app.hammer_radar.operator.betrayal_candle_archive import (
    build_betrayal_candle_archive,
    build_betrayal_candle_archive_status,
)
from src.app.hammer_radar.operator.betrayal_candle_capture import (
    backfill_betrayal_candle_capture,
    build_betrayal_candle_capture_status,
    capture_candles,
)
from src.app.hammer_radar.operator.betrayal_shadow_outcomes import (
    OUTCOMES_FILENAME,
    SHADOW_LOSS,
    SHADOW_NO_DATA,
    SHADOW_WIN,
)
from src.app.hammer_radar.operator.betrayal_shadow_resolver import (
    RESOLUTIONS_FILENAME,
    resolve_betrayal_shadow_outcomes,
)
from src.app.hammer_radar.operator.betrayal_strategy_audit import (
    BETRAYAL_PRIMARY_CANDIDATE,
    BETRAYAL_REJECTED,
    BETRAYAL_WATCHLIST,
    build_betrayal_strategy_audit,
    build_betrayal_strategy_row,
    invert_direction,
)
from src.app.hammer_radar.operator.models import OutcomeRecord, SignalRecord
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR


class BetrayalStrategyAuditTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict("os.environ", {LOG_DIR_ENV_VAR: str(self.log_dir)})
        self.env_patch.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_222m_like_row_becomes_primary_candidate(self) -> None:
        row = build_betrayal_strategy_row(self._row(timeframe="222m", sample_count=48, wins=6, total_pnl=-14.1309))

        self.assertEqual(BETRAYAL_PRIMARY_CANDIDATE, row["recommendation"])
        self.assertEqual(12.5, row["original"]["win_rate_pct"])
        self.assertEqual(87.5, row["betrayal"]["win_rate_pct"])
        self.assertEqual(14.1309, row["betrayal"]["total_pnl_pct"])
        self.assertEqual("short", row["betrayal_direction"])
        self.assertFalse(row["order_placed"])
        self.assertFalse(row["network_allowed"])

    def test_88m_like_row_becomes_watchlist_candidate(self) -> None:
        row = build_betrayal_strategy_row(self._row(timeframe="88m", sample_count=90, wins=33, total_pnl=-1.5995))

        self.assertEqual(BETRAYAL_WATCHLIST, row["recommendation"])
        self.assertEqual(36.67, row["original"]["win_rate_pct"])
        self.assertEqual(63.33, row["betrayal"]["win_rate_pct"])
        self.assertEqual(1.5995, row["betrayal"]["total_pnl_pct"])
        self.assertEqual("short", row["betrayal_direction"])

    def test_positive_original_total_pnl_is_rejected(self) -> None:
        row = build_betrayal_strategy_row(self._row(timeframe="13m", sample_count=48, wins=6, total_pnl=14.1309))

        self.assertEqual(BETRAYAL_REJECTED, row["recommendation"])
        self.assertIn("original total pnl is not negative", row["blockers"])
        self.assertLess(row["betrayal"]["total_pnl_pct"], 0)

    def test_low_sample_does_not_become_candidate(self) -> None:
        row = build_betrayal_strategy_row(self._row(timeframe="222m", sample_count=12, wins=1, total_pnl=-5.0))

        self.assertEqual(BETRAYAL_REJECTED, row["recommendation"])
        self.assertEqual("LOW_SAMPLE", row["confidence"])
        self.assertIn("sample_count below minimum 30", row["blockers"])

    def test_inverse_metrics_and_direction_are_computed(self) -> None:
        row = build_betrayal_strategy_row(self._row(timeframe="55m", direction="short", sample_count=40, wins=10, total_pnl=-8.0))

        self.assertEqual("long", row["betrayal_direction"])
        self.assertEqual(75.0, row["betrayal"]["win_rate_pct"])
        self.assertEqual(0.2, row["betrayal"]["avg_pnl_pct"])
        self.assertEqual(8.0, row["betrayal"]["total_pnl_pct"])
        self.assertEqual("short", invert_direction("long"))
        self.assertEqual("long", invert_direction("short"))

    def test_audit_payload_classifies_seeded_performance_rows(self) -> None:
        self._seed_group("primary-222m", "222m", "long", "ladder_close_50_618", wins=6, losses=42, total_pnl=-14.1309)
        self._seed_group("watch-88m", "88m", "long", "ladder_close_50_618", wins=33, losses=57, total_pnl=-1.5995)
        self._seed_group("normal-13m", "13m", "long", "ladder_close_50_618", wins=35, losses=13, total_pnl=8.0)

        payload = build_betrayal_strategy_audit(log_dir=self.log_dir)

        aggregate_primary = self._find(payload["timeframe_aggregate_primary_candidates"], timeframe="222m")
        aggregate_watchlist = self._find(payload["timeframe_aggregate_watchlist_candidates"], timeframe="88m")
        aggregate_rejected_normal = self._find(payload["timeframe_aggregate_rejected_candidates"], timeframe="13m")
        direction_primary = self._find(payload["direction_entry_mode_primary_candidates"], timeframe="222m")
        direction_watchlist = self._find(payload["direction_entry_mode_watchlist_candidates"], timeframe="88m")
        direction_rejected_normal = self._find(payload["direction_entry_mode_rejected_candidates"], timeframe="13m")
        legacy_primary = self._find(payload["primary_candidates"], timeframe="222m")
        legacy_watchlist = self._find(payload["watchlist_candidates"], timeframe="88m")
        self.assertEqual(BETRAYAL_PRIMARY_CANDIDATE, aggregate_primary["recommendation"])
        self.assertEqual("timeframe_aggregate", aggregate_primary["audit_scope"])
        self.assertIsNone(aggregate_primary["original_direction"])
        self.assertIsNone(aggregate_primary["entry_mode"])
        self.assertEqual(BETRAYAL_WATCHLIST, aggregate_watchlist["recommendation"])
        self.assertEqual("timeframe_aggregate", aggregate_watchlist["audit_scope"])
        self.assertEqual(BETRAYAL_REJECTED, aggregate_rejected_normal["recommendation"])
        self.assertEqual(BETRAYAL_PRIMARY_CANDIDATE, direction_primary["recommendation"])
        self.assertEqual("direction_entry_mode", direction_primary["audit_scope"])
        self.assertEqual(BETRAYAL_WATCHLIST, direction_watchlist["recommendation"])
        self.assertEqual("direction_entry_mode", direction_watchlist["audit_scope"])
        self.assertEqual(BETRAYAL_REJECTED, direction_rejected_normal["recommendation"])
        self.assertEqual(direction_primary, legacy_primary)
        self.assertEqual(direction_watchlist, legacy_watchlist)
        for key in (
            "timeframe_aggregate_leaderboard",
            "timeframe_aggregate_primary_candidates",
            "timeframe_aggregate_watchlist_candidates",
            "timeframe_aggregate_rejected_candidates",
            "direction_entry_mode_leaderboard",
            "direction_entry_mode_primary_candidates",
            "direction_entry_mode_watchlist_candidates",
            "direction_entry_mode_rejected_candidates",
        ):
            self.assertIn(key, payload)
        self.assertFalse(payload["live_execution_enabled"])
        self.assertFalse(payload["allow_live_orders"])
        self.assertTrue(payload["global_kill_switch"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["execution_attempted"])
        self.assertFalse(payload["order_payload_created"])
        self.assertFalse(payload["network_allowed"])
        self.assertFalse(payload["secrets_shown"])

    def test_api_endpoint_returns_safe_fields(self) -> None:
        self._seed_group("primary-222m", "222m", "long", "ladder_close_50_618", wins=6, losses=42, total_pnl=-14.1309)

        response = self.client.get("/strategy-performance/betrayal-audit")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("OK", payload["status"])
        self.assertEqual("R80", payload["phase"])
        aggregate_primary = self._find(payload["timeframe_aggregate_primary_candidates"], timeframe="222m")
        self.assertEqual(BETRAYAL_PRIMARY_CANDIDATE, aggregate_primary["recommendation"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["execution_attempted"])
        self.assertFalse(payload["order_payload_created"])
        self.assertFalse(payload["network_allowed"])
        self.assertFalse(payload["secrets_shown"])

    def test_cli_report_includes_primary_and_watchlist(self) -> None:
        self._seed_group("primary-222m", "222m", "long", "ladder_close_50_618", wins=6, losses=42, total_pnl=-14.1309)
        self._seed_group("watch-88m", "88m", "long", "ladder_close_50_618", wins=33, losses=57, total_pnl=-1.5995)

        result = run(
            [
                ".venv/bin/python",
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                str(self.log_dir),
                "betrayal-strategy-audit",
            ],
            cwd=Path(__file__).resolve().parents[2],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(0, result.returncode, msg=result.stderr)
        self.assertIn("TIMEFRAME AGGREGATE BETRAYAL", result.stdout)
        self.assertIn("DIRECTION / ENTRY-MODE BETRAYAL", result.stdout)
        self.assertIn("BETRAYAL_PRIMARY_CANDIDATE", result.stdout)
        self.assertIn("BETRAYAL_WATCHLIST", result.stdout)
        self.assertIn("222m aggregate", result.stdout)
        self.assertIn("88m aggregate", result.stdout)
        self.assertIn("222m long->short ladder_close_50_618", result.stdout)
        self.assertIn("88m long->short ladder_close_50_618", result.stdout)
        self.assertIn("No order placed", result.stdout)

    def test_existing_strategy_performance_and_betrayal_shadow_endpoints_still_pass(self) -> None:
        self._seed_group("normal-13m", "13m", "long", "ladder_close_50_618", wins=35, losses=13, total_pnl=8.0)

        for path in (
            "/strategy-performance/summary",
            "/strategy-performance/timeframes",
            "/strategy-performance/entry-modes",
            "/strategy-performance/live-eligibility",
            "/betrayal-shadow/outcomes",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(200, response.status_code)
                payload = response.json()
                self.assertFalse(payload["live_execution_enabled"])
                self.assertFalse(payload["order_placed"])

    def test_r81_endpoint_returns_safe_fields_and_aggregate_targets_without_true_inverse_records(self) -> None:
        self._seed_group("primary-222m", "222m", "long", "ladder_close_50_618", wins=6, losses=42, total_pnl=-14.1309)
        self._seed_group("watch-88m", "88m", "long", "ladder_close_50_618", wins=33, losses=57, total_pnl=-1.5995)

        response = self.client.get("/strategy-performance/betrayal-inverse-validation")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("OK", payload["status"])
        self.assertEqual("R81", payload["phase"])
        self.assertEqual("TRUE_INVERSE_PAPER_OUTCOME_VALIDATION_ONLY_NO_ORDER", payload["execution_mode"])
        primary = self._find(payload["timeframe_aggregate_validations"], timeframe="222m")
        watchlist = self._find(payload["timeframe_aggregate_validations"], timeframe="88m")
        self.assertEqual(BETRAYAL_PRIMARY_CANDIDATE, primary["source_recommendation"])
        self.assertEqual(BETRAYAL_WATCHLIST, watchlist["source_recommendation"])
        self.assertEqual(TRUE_INVERSE_NO_DATA, primary["validation_status"])
        self.assertEqual(TRUE_INVERSE_NO_DATA, watchlist["validation_status"])
        self.assertFalse(payload["live_execution_enabled"])
        self.assertFalse(payload["allow_live_orders"])
        self.assertTrue(payload["global_kill_switch"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["execution_attempted"])
        self.assertFalse(payload["order_payload_created"])
        self.assertFalse(payload["network_allowed"])
        self.assertFalse(payload["secrets_shown"])

    def test_r81_cli_report_includes_aggregate_targets_and_no_order_note(self) -> None:
        self._seed_group("primary-222m", "222m", "long", "ladder_close_50_618", wins=6, losses=42, total_pnl=-14.1309)
        self._seed_group("watch-88m", "88m", "long", "ladder_close_50_618", wins=33, losses=57, total_pnl=-1.5995)

        result = run(
            [
                ".venv/bin/python",
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                str(self.log_dir),
                "betrayal-inverse-validation",
            ],
            cwd=Path(__file__).resolve().parents[2],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(0, result.returncode, msg=result.stderr)
        self.assertIn("R81 true inverse validation: OK", result.stdout)
        self.assertIn("TIMEFRAME AGGREGATE TRUE INVERSE VALIDATION", result.stdout)
        self.assertIn("DIRECTION / ENTRY-MODE TRUE INVERSE VALIDATION", result.stdout)
        self.assertIn("222m aggregate", result.stdout)
        self.assertIn("88m aggregate", result.stdout)
        self.assertIn("TRUE_INVERSE_NO_DATA", result.stdout)
        self.assertIn("No order placed", result.stdout)

    def test_r81_true_inverse_sample_below_threshold_is_insufficient(self) -> None:
        self._seed_group("primary-222m", "222m", "long", "ladder_close_50_618", wins=6, losses=42, total_pnl=-14.1309)
        self._write_shadow_records(
            [
                self._shadow_record("222m", index=index, status=SHADOW_WIN, pnl_pct=0.2)
                for index in range(5)
            ]
        )

        payload = build_betrayal_inverse_validation(log_dir=self.log_dir)

        primary = self._find(payload["timeframe_aggregate_validations"], timeframe="222m")
        self.assertEqual(5, primary["true_inverse_sample_count"])
        self.assertEqual(INSUFFICIENT_TRUE_INVERSE_OUTCOMES, primary["validation_status"])
        self.assertFalse(primary["live_execution_enabled"])
        self.assertFalse(primary["order_placed"])

    def test_r81_true_inverse_passing_sample_can_validate_primary_in_fixture(self) -> None:
        self._seed_group("primary-222m", "222m", "long", "ladder_close_50_618", wins=6, losses=42, total_pnl=-14.1309)
        records = [
            self._shadow_record("222m", index=index, status=SHADOW_WIN, pnl_pct=0.3)
            for index in range(18)
        ]
        records.extend(
            self._shadow_record("222m", index=index + 18, status=SHADOW_LOSS, pnl_pct=-0.1)
            for index in range(12)
        )
        self._write_shadow_records(records)

        payload = build_betrayal_inverse_validation(log_dir=self.log_dir)

        primary = self._find(payload["timeframe_aggregate_validations"], timeframe="222m")
        self.assertEqual(30, primary["true_inverse_sample_count"])
        self.assertEqual(60.0, primary["true_inverse_win_rate_pct"])
        self.assertEqual(TRUE_INVERSE_VALIDATED_PRIMARY, primary["validation_status"])
        self.assertFalse(primary["real_order_placed"])

    def test_r81_true_inverse_failed_sample_is_rejected(self) -> None:
        self._seed_group("primary-222m", "222m", "long", "ladder_close_50_618", wins=6, losses=42, total_pnl=-14.1309)
        records = [
            self._shadow_record("222m", index=index, status=SHADOW_WIN, pnl_pct=0.1)
            for index in range(10)
        ]
        records.extend(
            self._shadow_record("222m", index=index + 10, status=SHADOW_LOSS, pnl_pct=-0.2)
            for index in range(20)
        )
        self._write_shadow_records(records)

        payload = build_betrayal_inverse_validation(log_dir=self.log_dir)

        primary = self._find(payload["timeframe_aggregate_validations"], timeframe="222m")
        self.assertEqual(30, primary["true_inverse_sample_count"])
        self.assertEqual(TRUE_INVERSE_REJECTED, primary["validation_status"])
        self.assertIn("true_inverse_win_rate_pct below minimum 55.0", primary["blockers"])

    def test_r81_aggregates_by_timeframe_and_direction(self) -> None:
        self._seed_group("primary-222m", "222m", "long", "ladder_close_50_618", wins=6, losses=42, total_pnl=-14.1309)
        self._write_shadow_records(
            [
                self._shadow_record("222m", index=0, status=SHADOW_WIN, pnl_pct=0.2, original_direction="long", shadow_direction="short"),
                self._shadow_record("222m", index=1, status=SHADOW_WIN, pnl_pct=0.2, original_direction="short", shadow_direction="long"),
            ]
        )

        payload = build_betrayal_inverse_validation(log_dir=self.log_dir, min_true_inverse_sample=1)

        aggregate = self._find(payload["timeframe_aggregate_validations"], timeframe="222m")
        direction = self._find(payload["direction_entry_mode_validations"], timeframe="222m")
        self.assertEqual(2, aggregate["true_inverse_sample_count"])
        self.assertEqual(1, direction["true_inverse_sample_count"])

    def test_r81_1_resolver_payload_returns_safe_fields_and_no_data_without_candles(self) -> None:
        self._write_shadow_records([self._unresolved_shadow_record("222m", index=0)])

        payload = resolve_betrayal_shadow_outcomes(log_dir=self.log_dir, limit=10)

        self.assertEqual("OK", payload["status"])
        self.assertEqual("R81.1", payload["phase"])
        self.assertEqual("BETRAYAL_SHADOW_OUTCOME_RESOLVER_ONLY_NO_ORDER", payload["execution_mode"])
        self.assertEqual(1, payload["scanned_records"])
        self.assertEqual(0, payload["newly_resolved_records"])
        self.assertEqual(1, payload["no_data_records"])
        self.assertFalse(payload["live_execution_enabled"])
        self.assertFalse(payload["allow_live_orders"])
        self.assertTrue(payload["global_kill_switch"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["execution_attempted"])
        self.assertFalse(payload["order_payload_created"])
        self.assertFalse(payload["network_allowed"])
        self.assertFalse(payload["secrets_shown"])

    def test_r81_1_dry_run_and_write_false_do_not_persist(self) -> None:
        self._write_shadow_records([self._unresolved_shadow_record("222m", index=0)])
        self._write_candles([self._candle("222m", high=106.0, low=99.0)])

        dry_run = resolve_betrayal_shadow_outcomes(log_dir=self.log_dir, dry_run=True, write=True)
        no_write = resolve_betrayal_shadow_outcomes(log_dir=self.log_dir, dry_run=False, write=False)

        self.assertEqual(1, dry_run["newly_resolved_records"])
        self.assertEqual(1, no_write["newly_resolved_records"])
        self.assertFalse((self.log_dir / RESOLUTIONS_FILENAME).exists())

    def test_r81_1_write_true_persists_resolution_output_only_when_explicit(self) -> None:
        self._write_shadow_records([self._unresolved_shadow_record("222m", index=0)])
        self._write_candles([self._candle("222m", high=106.0, low=99.0)])

        payload = resolve_betrayal_shadow_outcomes(log_dir=self.log_dir, dry_run=False, write=True)

        self.assertTrue(payload["persisted"])
        self.assertEqual(1, payload["newly_resolved_records"])
        records = self._read_jsonl(self.log_dir / RESOLUTIONS_FILENAME)
        self.assertEqual(1, len(records))
        self.assertEqual(SHADOW_WIN, records[0]["shadow_status"])
        self.assertFalse(records[0]["order_placed"])

    def test_r81_1_tp_first_resolves_as_win(self) -> None:
        self._write_shadow_records([self._unresolved_shadow_record("222m", index=0)])
        self._write_candles([self._candle("222m", high=106.0, low=99.0)])

        payload = resolve_betrayal_shadow_outcomes(log_dir=self.log_dir)

        record = payload["records"][0]
        self.assertEqual(SHADOW_WIN, record["shadow_status"])
        self.assertEqual(5.0, record["shadow_pnl_pct"])

    def test_r81_1_sl_first_resolves_as_loss(self) -> None:
        self._write_shadow_records([self._unresolved_shadow_record("222m", index=0)])
        self._write_candles([self._candle("222m", high=101.0, low=94.0)])

        payload = resolve_betrayal_shadow_outcomes(log_dir=self.log_dir)

        record = payload["records"][0]
        self.assertEqual(SHADOW_LOSS, record["shadow_status"])
        self.assertEqual(-5.0, record["shadow_pnl_pct"])

    def test_r81_1_same_candle_tp_sl_ambiguity_is_conservative_loss(self) -> None:
        self._write_shadow_records([self._unresolved_shadow_record("222m", index=0)])
        self._write_candles([self._candle("222m", high=106.0, low=94.0)])

        payload = resolve_betrayal_shadow_outcomes(log_dir=self.log_dir)

        record = payload["records"][0]
        self.assertEqual(SHADOW_LOSS, record["shadow_status"])
        self.assertEqual("stop", record["shadow_close_reason"])

    def test_r81_1_already_resolved_records_are_not_duplicated(self) -> None:
        self._write_shadow_records([self._unresolved_shadow_record("222m", index=0)])
        self._write_candles([self._candle("222m", high=106.0, low=99.0)])

        first = resolve_betrayal_shadow_outcomes(log_dir=self.log_dir, dry_run=False, write=True)
        second = resolve_betrayal_shadow_outcomes(log_dir=self.log_dir, dry_run=False, write=True)

        self.assertEqual(1, first["newly_resolved_records"])
        self.assertEqual(0, second["newly_resolved_records"])
        self.assertEqual(1, second["already_resolved_records"])
        self.assertEqual(1, len(self._read_jsonl(self.log_dir / RESOLUTIONS_FILENAME)))

    def test_r81_1_timeframe_aggregation_works_for_222m_and_88m(self) -> None:
        self._write_shadow_records(
            [
                self._unresolved_shadow_record("222m", index=0),
                self._unresolved_shadow_record("88m", index=1),
            ]
        )
        self._write_candles(
            [
                self._candle("222m", high=106.0, low=99.0),
                self._candle("88m", high=106.0, low=99.0),
            ]
        )

        payload = resolve_betrayal_shadow_outcomes(log_dir=self.log_dir)

        self.assertEqual(1, payload["target_summary"]["222m"]["resolved_records"])
        self.assertEqual(1, payload["target_summary"]["88m"]["resolved_records"])

    def test_r81_validation_consumes_resolver_output(self) -> None:
        self._seed_group("primary-222m", "222m", "long", "ladder_close_50_618", wins=6, losses=42, total_pnl=-14.1309)
        self._write_shadow_records([self._unresolved_shadow_record("222m", index=0)])
        self._write_candles([self._candle("222m", high=106.0, low=99.0)])
        resolve_betrayal_shadow_outcomes(log_dir=self.log_dir, dry_run=False, write=True)

        payload = build_betrayal_inverse_validation(log_dir=self.log_dir)

        primary = self._find(payload["timeframe_aggregate_validations"], timeframe="222m")
        self.assertEqual(1, primary["true_inverse_sample_count"])
        self.assertEqual(INSUFFICIENT_TRUE_INVERSE_OUTCOMES, primary["validation_status"])

    def test_r81_1_api_endpoints_are_safe(self) -> None:
        self._write_shadow_records([self._unresolved_shadow_record("222m", index=0)])

        resolve_response = self.client.post(
            "/betrayal-shadow/resolve",
            json={"dry_run": True, "write": False, "limit": 20},
        )
        resolutions_response = self.client.get("/betrayal-shadow/resolutions")

        self.assertEqual(200, resolve_response.status_code)
        self.assertEqual(200, resolutions_response.status_code)
        self.assertFalse(resolve_response.json()["order_placed"])
        self.assertFalse(resolve_response.json()["network_allowed"])
        self.assertFalse(resolutions_response.json()["order_placed"])

    def test_r81_1_cli_command_exists(self) -> None:
        self._write_shadow_records([self._unresolved_shadow_record("222m", index=0)])

        result = run(
            [
                ".venv/bin/python",
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                str(self.log_dir),
                "betrayal-shadow-resolve",
                "--limit",
                "20",
            ],
            cwd=Path(__file__).resolve().parents[2],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(0, result.returncode, msg=result.stderr)
        self.assertIn("R81.1 betrayal shadow resolver: OK", result.stdout)
        self.assertIn("scanned_records: 1", result.stdout)
        self.assertIn("No order placed", result.stdout)

    def test_r81_2_candle_archive_payload_returns_safe_fields(self) -> None:
        self._write_shadow_records([self._unresolved_shadow_record("222m", index=0)])
        self._write_candles([self._candle("222m", high=106.0, low=99.0)])

        payload = build_betrayal_candle_archive(log_dir=self.log_dir)

        self.assertEqual("OK", payload["status"])
        self.assertEqual("R81.2", payload["phase"])
        self.assertEqual("BETRAYAL_CANDLE_ARCHIVE_REPLAY_BRIDGE_ONLY_NO_ORDER", payload["execution_mode"])
        self.assertEqual(1, payload["candles_found"])
        self.assertEqual(0, payload["candles_written"])
        self.assertFalse(payload["live_execution_enabled"])
        self.assertFalse(payload["allow_live_orders"])
        self.assertTrue(payload["global_kill_switch"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["execution_attempted"])
        self.assertFalse(payload["order_payload_created"])
        self.assertFalse(payload["network_allowed"])
        self.assertFalse(payload["secrets_shown"])

    def test_r81_2_dry_run_and_write_false_do_not_write_archive_files(self) -> None:
        self._write_candles([self._candle("222m", high=106.0, low=99.0)])

        dry_run = build_betrayal_candle_archive(log_dir=self.log_dir, dry_run=True, write=True)
        no_write = build_betrayal_candle_archive(log_dir=self.log_dir, dry_run=False, write=False)

        self.assertEqual(1, dry_run["candles_found"])
        self.assertEqual(1, no_write["candles_found"])
        self.assertFalse((self.log_dir / "candle_archive").exists())

    def test_r81_2_write_true_writes_local_archive_only_and_dedupes(self) -> None:
        self._write_candles(
            [
                self._candle("222m", high=106.0, low=99.0),
                self._candle("222m", high=106.0, low=99.0),
            ]
        )

        payload = build_betrayal_candle_archive(log_dir=self.log_dir, dry_run=False, write=True)
        second = build_betrayal_candle_archive(log_dir=self.log_dir, dry_run=False, write=True)

        archive_path = self.log_dir / "candle_archive" / "BTCUSDT_222m.ndjson"
        self.assertTrue(archive_path.exists())
        self.assertEqual(1, payload["candles_written"])
        self.assertEqual(0, second["candles_written"])
        self.assertEqual(1, len(self._read_jsonl(archive_path)))

    def test_r81_2_archive_status_reports_available_candles(self) -> None:
        self._write_candles([self._candle("222m", high=106.0, low=99.0)])
        build_betrayal_candle_archive(log_dir=self.log_dir, dry_run=False, write=True)

        payload = build_betrayal_candle_archive_status(log_dir=self.log_dir)

        self.assertEqual("OK", payload["status"])
        self.assertEqual(1, payload["available"][0]["candle_count"])
        self.assertEqual("222m", payload["available"][0]["timeframe"])

    def test_r81_2_missing_archive_keeps_resolver_no_data_behavior(self) -> None:
        self._write_shadow_records([self._unresolved_shadow_record("222m", index=0)])

        payload = resolve_betrayal_shadow_outcomes(log_dir=self.log_dir)

        self.assertEqual(0, payload["newly_resolved_records"])
        self.assertEqual(1, payload["no_data_records"])

    def test_r81_2_resolver_consumes_archive_candles(self) -> None:
        self._write_shadow_records([self._unresolved_shadow_record("222m", index=0)])
        self._write_candles([self._candle("222m", high=106.0, low=99.0)])
        build_betrayal_candle_archive(log_dir=self.log_dir, dry_run=False, write=True)
        (self.log_dir / "candles.ndjson").unlink()

        payload = resolve_betrayal_shadow_outcomes(log_dir=self.log_dir)

        self.assertEqual(1, payload["newly_resolved_records"])
        self.assertEqual(SHADOW_WIN, payload["records"][0]["shadow_status"])

    def test_r81_2_archive_tp_sl_and_same_candle_resolution_paths(self) -> None:
        for high, low, expected in ((106.0, 99.0, SHADOW_WIN), (101.0, 94.0, SHADOW_LOSS), (106.0, 94.0, SHADOW_LOSS)):
            with self.subTest(high=high, low=low):
                temp_dir = tempfile.TemporaryDirectory()
                case_dir = Path(temp_dir.name)
                self._write_shadow_records_to(case_dir, [self._unresolved_shadow_record("222m", index=0)])
                self._write_candles_to(case_dir, [self._candle("222m", high=high, low=low)])
                build_betrayal_candle_archive(log_dir=case_dir, dry_run=False, write=True)
                (case_dir / "candles.ndjson").unlink()

                payload = resolve_betrayal_shadow_outcomes(log_dir=case_dir)

                self.assertEqual(expected, payload["records"][0]["shadow_status"])
                temp_dir.cleanup()

    def test_r81_2_target_coverage_reports_222m_88m_and_55m(self) -> None:
        self._write_shadow_records(
            [
                self._unresolved_shadow_record("222m", index=0),
                self._unresolved_shadow_record("88m", index=1),
                self._unresolved_shadow_record("55m", index=2),
            ]
        )
        self._write_candles(
            [
                self._candle("222m", high=106.0, low=99.0),
                self._candle("88m", high=106.0, low=99.0),
                self._candle("55m", high=106.0, low=99.0),
            ]
        )

        payload = build_betrayal_candle_archive(log_dir=self.log_dir)

        self.assertEqual(1, payload["target_coverage"]["222m"]["covered_records"])
        self.assertEqual(1, payload["target_coverage"]["88m"]["covered_records"])
        self.assertEqual(1, payload["target_coverage"]["55m"]["covered_records"])

    def test_r81_2_api_endpoints_are_safe(self) -> None:
        self._write_candles([self._candle("222m", high=106.0, low=99.0)])

        build_response = self.client.post(
            "/betrayal-shadow/candle-archive/build",
            json={"dry_run": True, "write": False, "limit": 20},
        )
        status_response = self.client.get("/betrayal-shadow/candle-archive/status")

        self.assertEqual(200, build_response.status_code)
        self.assertEqual(200, status_response.status_code)
        self.assertEqual("R81.2", build_response.json()["phase"])
        self.assertFalse(build_response.json()["order_placed"])
        self.assertFalse(build_response.json()["network_allowed"])
        self.assertFalse(status_response.json()["order_placed"])

    def test_r81_2_cli_command_exists(self) -> None:
        self._write_candles([self._candle("222m", high=106.0, low=99.0)])

        result = run(
            [
                ".venv/bin/python",
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                str(self.log_dir),
                "betrayal-candle-archive",
                "--limit",
                "20",
            ],
            cwd=Path(__file__).resolve().parents[2],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(0, result.returncode, msg=result.stderr)
        self.assertIn("R81.2 betrayal candle archive: OK", result.stdout)
        self.assertIn("candles_found: 1", result.stdout)
        self.assertIn("No order placed", result.stdout)

    def test_r81_3_capture_backfill_payload_safety_and_no_source_zero(self) -> None:
        self._write_shadow_records([self._unresolved_shadow_record("222m", index=0)])

        payload = backfill_betrayal_candle_capture(log_dir=self.log_dir)

        self.assertEqual("OK", payload["status"])
        self.assertEqual("R81.3", payload["phase"])
        self.assertEqual("SAFE_CANDLE_CAPTURE_BACKFILL_ONLY_NO_ORDER", payload["execution_mode"])
        self.assertEqual("LOCAL_ONLY", payload["source_mode"])
        self.assertEqual(0, payload["candles_found"])
        self.assertEqual(0, payload["candles_written"])
        self.assertFalse(payload["live_execution_enabled"])
        self.assertFalse(payload["allow_live_orders"])
        self.assertTrue(payload["global_kill_switch"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["execution_attempted"])
        self.assertFalse(payload["order_payload_created"])
        self.assertFalse(payload["network_allowed"])
        self.assertFalse(payload["secrets_shown"])

    def test_r81_3_dry_run_and_write_false_do_not_write(self) -> None:
        self._write_candles([self._candle("222m", high=106.0, low=99.0)])

        dry_run = backfill_betrayal_candle_capture(log_dir=self.log_dir, dry_run=True, write=True)
        no_write = backfill_betrayal_candle_capture(log_dir=self.log_dir, dry_run=False, write=False)

        self.assertEqual(1, dry_run["candles_found"])
        self.assertEqual(1, no_write["candles_found"])
        self.assertFalse((self.log_dir / "candle_archive").exists())

    def test_r81_3_write_true_writes_archive_and_skips_duplicates(self) -> None:
        self._write_candles(
            [
                self._candle("222m", high=106.0, low=99.0),
                self._candle("222m", high=106.0, low=99.0),
            ]
        )

        payload = backfill_betrayal_candle_capture(log_dir=self.log_dir, dry_run=False, write=True)
        second = backfill_betrayal_candle_capture(log_dir=self.log_dir, dry_run=False, write=True)

        self.assertEqual(1, payload["candles_written"])
        self.assertEqual(0, second["candles_written"])
        self.assertEqual(1, len(self._read_jsonl(self.log_dir / "candle_archive" / "BTCUSDT_222m.ndjson")))

    def test_r81_3_target_coverage_before_after_works(self) -> None:
        self._write_shadow_records([self._unresolved_shadow_record("222m", index=0)])
        self._write_candles([self._candle("222m", high=106.0, low=99.0)])

        payload = backfill_betrayal_candle_capture(log_dir=self.log_dir, dry_run=True, write=False)

        self.assertEqual(0, payload["target_coverage_before"]["222m"]["covered_records"])
        self.assertEqual(1, payload["target_coverage_after"]["222m"]["covered_records"])

    def test_r81_3_capture_candles_writes_local_archive(self) -> None:
        payload = capture_candles([self._candle("222m", high=106.0, low=99.0)], log_dir=self.log_dir)

        self.assertEqual(1, payload["candles_written"])
        self.assertTrue((self.log_dir / "candle_archive" / "BTCUSDT_222m.ndjson").exists())
        self.assertFalse(payload["order_placed"])

    def test_r81_3_resolver_can_resolve_after_capture_created_archive(self) -> None:
        self._write_shadow_records([self._unresolved_shadow_record("222m", index=0)])
        capture_candles([self._candle("222m", high=106.0, low=99.0)], log_dir=self.log_dir)

        payload = resolve_betrayal_shadow_outcomes(log_dir=self.log_dir)

        self.assertEqual(1, payload["newly_resolved_records"])
        self.assertEqual(SHADOW_WIN, payload["records"][0]["shadow_status"])

    def test_r81_3_api_endpoints_are_safe(self) -> None:
        self._write_candles([self._candle("222m", high=106.0, low=99.0)])

        backfill_response = self.client.post(
            "/betrayal-shadow/candle-capture/backfill",
            json={"dry_run": True, "write": False, "limit": 20, "source_mode": "LOCAL_ONLY"},
        )
        status_response = self.client.get("/betrayal-shadow/candle-capture/status")

        self.assertEqual(200, backfill_response.status_code)
        self.assertEqual(200, status_response.status_code)
        self.assertEqual("R81.3", backfill_response.json()["phase"])
        self.assertFalse(backfill_response.json()["order_placed"])
        self.assertFalse(backfill_response.json()["network_allowed"])
        self.assertTrue(status_response.json()["capture_hook_exists"])

    def test_r81_3_cli_command_exists(self) -> None:
        self._write_candles([self._candle("222m", high=106.0, low=99.0)])

        result = run(
            [
                ".venv/bin/python",
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                str(self.log_dir),
                "betrayal-candle-capture",
                "--limit",
                "20",
            ],
            cwd=Path(__file__).resolve().parents[2],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(0, result.returncode, msg=result.stderr)
        self.assertIn("R81.3 betrayal candle capture: OK", result.stdout)
        self.assertIn("source_mode: LOCAL_ONLY", result.stdout)
        self.assertIn("candles_found: 1", result.stdout)
        self.assertIn("No order placed", result.stdout)

    def test_r81_3_capture_status_reports_hook_and_coverage(self) -> None:
        self._write_shadow_records([self._unresolved_shadow_record("222m", index=0)])
        capture_candles([self._candle("222m", high=106.0, low=99.0)], log_dir=self.log_dir)

        payload = build_betrayal_candle_capture_status(log_dir=self.log_dir)

        self.assertTrue(payload["capture_hook_exists"])
        self.assertEqual(1, payload["target_coverage"]["222m"]["covered_records"])

    @staticmethod
    def _row(*, timeframe: str, sample_count: int, wins: int, total_pnl: float, direction: str = "long") -> dict:
        losses = sample_count - wins
        return {
            "timeframe": timeframe,
            "direction": direction,
            "entry_mode": "ladder_close_50_618",
            "sample_count": sample_count,
            "wins": wins,
            "losses": losses,
            "win_rate_pct": round((wins / sample_count) * 100.0, 2),
            "avg_pnl_pct": round(total_pnl / sample_count, 4),
            "total_pnl_pct": round(total_pnl, 4),
            "best_pnl_pct": 0.5,
            "worst_pnl_pct": -0.5,
            "max_losing_streak": losses,
            "recommendation": "BLOCKED_FROM_LIVE",
        }

    @staticmethod
    def _find(rows: list[dict], **filters: str) -> dict:
        for row in rows:
            if all(row.get(key) == value for key, value in filters.items()):
                return row
        raise AssertionError(f"row not found: {filters}")

    def _seed_group(
        self,
        prefix: str,
        timeframe: str,
        direction: str,
        entry_mode: str,
        *,
        wins: int,
        losses: int,
        total_pnl: float,
    ) -> None:
        sample_count = wins + losses
        win_pnl = 0.1
        loss_pnl = (total_pnl - wins * win_pnl) / losses if losses else 0.0
        pnl_values = [win_pnl] * wins + [loss_pnl] * losses
        base_time = datetime.now(UTC) - timedelta(hours=4)
        for index, pnl_pct in enumerate(pnl_values):
            timestamp = (base_time + timedelta(minutes=index)).isoformat()
            signal_id = f"BTCUSDT|{timeframe}|{direction}|{prefix}-{index}"
            signal = SignalRecord(
                signal_id=signal_id,
                symbol="BTCUSDT",
                timeframe=timeframe,
                direction=direction,
                timestamp=timestamp,
                hammer_strength=90.0,
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
        self.assertEqual(sample_count, len(pnl_values))

    def _write_shadow_records(self, records: list[dict]) -> None:
        self._write_shadow_records_to(self.log_dir, records)

    @staticmethod
    def _write_shadow_records_to(log_dir: Path, records: list[dict]) -> None:
        path = log_dir / OUTCOMES_FILENAME
        with path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, sort_keys=True) + "\n")

    def _write_candles(self, records: list[dict]) -> None:
        self._write_candles_to(self.log_dir, records)

    @staticmethod
    def _write_candles_to(log_dir: Path, records: list[dict]) -> None:
        path = log_dir / "candles.ndjson"
        with path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, sort_keys=True) + "\n")

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict]:
        with path.open("r", encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    @staticmethod
    def _unresolved_shadow_record(timeframe: str, *, index: int) -> dict:
        return {
            "shadow_outcome_id": f"shadow-{timeframe}-{index}",
            "created_at": datetime.now(UTC).isoformat(),
            "source": "test",
            "original_signal_id": f"signal-{timeframe}-{index}",
            "original_direction": "short",
            "shadow_direction": "long",
            "symbol": "BTCUSDT",
            "timeframe": timeframe,
            "signal_timestamp": "2026-05-01T00:00:00+00:00",
            "shadow_entry": 100.0,
            "shadow_stop": 95.0,
            "shadow_take_profit": 105.0,
            "shadow_status": SHADOW_NO_DATA,
            "shadow_pnl_pct": None,
            "shadow_pnl_usd": None,
            "comparison": {"inconclusive": True, "shadow_better": False, "original_better": False},
            "live_execution_enabled": False,
            "order_placed": False,
            "shadow_only": True,
        }

    @staticmethod
    def _candle(timeframe: str, *, high: float, low: float) -> dict:
        return {
            "symbol": "BTCUSDT",
            "timeframe": timeframe,
            "timestamp": "2026-05-01T00:01:00+00:00",
            "open": 100.0,
            "high": high,
            "low": low,
            "close": 100.0,
        }

    @staticmethod
    def _shadow_record(
        timeframe: str,
        *,
        index: int,
        status: str,
        pnl_pct: float,
        original_direction: str = "long",
        shadow_direction: str = "short",
    ) -> dict:
        return {
            "shadow_outcome_id": f"shadow-{timeframe}-{index}",
            "created_at": datetime.now(UTC).isoformat(),
            "source": "test",
            "original_signal_id": f"signal-{timeframe}-{index}",
            "original_direction": original_direction,
            "shadow_direction": shadow_direction,
            "symbol": "BTCUSDT",
            "timeframe": timeframe,
            "signal_timestamp": datetime.now(UTC).isoformat(),
            "shadow_status": status,
            "shadow_pnl_pct": pnl_pct,
            "shadow_pnl_usd": None,
            "comparison": {"shadow_better": status == SHADOW_WIN, "original_better": status == SHADOW_LOSS},
            "live_execution_enabled": False,
            "order_placed": False,
            "shadow_only": True,
        }


if __name__ == "__main__":
    unittest.main()
