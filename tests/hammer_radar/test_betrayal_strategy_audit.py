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
    build_betrayal_shadow_resolutions_payload,
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
from src.app.hammer_radar.operator.markov_regime_gate import (
    BEAR_TREND,
    BULL_TREND,
    HIGH_VOLATILITY,
    INSUFFICIENT_DATA,
    LOW_VOLATILITY,
    RANGE,
    REGIME_NEUTRAL_OR_INSUFFICIENT_DATA,
    REGIME_PENDING_MORE_CANDLES,
    REGIME_REJECTS_CANDIDATE,
    REGIME_SUPPORTS_CANDIDATE,
    build_markov_regime_gate,
    classify_markov_regime,
)
from src.app.hammer_radar.operator.miro_fish_quality_gate import (
    FISH_BLOCKED,
    FISH_PASS,
    MIRO_FISH_BLOCKED,
    MIRO_FISH_NEEDS_MORE_EVIDENCE,
    MIRO_FISH_REJECTS_CANDIDATE,
    MIRO_FISH_SUPPORTS_CANDIDATE,
    build_miro_fish_quality_gate,
)
from src.app.hammer_radar.operator.live_arming_preflight import (
    BLOCKED_BY_MISSING_OPERATOR_APPROVAL,
    BLOCKED_BY_STRATEGY_QUALITY,
    build_live_arming_preflight,
)
from src.app.hammer_radar.operator.tiny_live_risk_contract import (
    RISK_CONTRACT_INVALID,
    RISK_CONTRACT_VALID_FOR_PREFLIGHT,
    build_tiny_live_risk_contract_payload,
    validate_risk_contract,
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

    def test_r81_4_candle_before_signal_timestamp_cannot_resolve(self) -> None:
        self._write_shadow_records([self._unresolved_shadow_record("222m", index=0)])
        self._write_candles(
            [
                self._candle_at(
                    "222m",
                    timestamp="2026-04-30T23:59:00+00:00",
                    high=106.0,
                    low=99.0,
                )
            ]
        )

        payload = resolve_betrayal_shadow_outcomes(log_dir=self.log_dir)

        self.assertEqual(0, payload["newly_resolved_records"])
        self.assertEqual(1, payload["no_data_records"])
        self.assertIn("no_temporally_aligned_candles", payload["blockers"])
        self.assertEqual(0, payload["target_summary"]["222m"]["resolved_records"])

    def test_r81_4_april_signal_cannot_resolve_from_may_candle(self) -> None:
        april_signal = self._unresolved_shadow_record("222m", index=0)
        april_signal["signal_timestamp"] = "2026-04-29T12:00:00+00:00"
        self._write_shadow_records([april_signal])
        self._write_candles(
            [
                self._candle_at(
                    "222m",
                    timestamp="2026-05-13T12:00:00+00:00",
                    high=106.0,
                    low=99.0,
                )
            ]
        )

        payload = resolve_betrayal_shadow_outcomes(log_dir=self.log_dir)

        self.assertEqual(0, payload["newly_resolved_records"])
        self.assertEqual(1, payload["no_data_records"])
        self.assertIn("no_temporally_aligned_candles", payload["blockers"])
        self.assertEqual(0, payload["resolution_summary"]["resolved_records"])

    def test_r81_4_candle_after_evaluation_window_cannot_resolve(self) -> None:
        self._write_shadow_records([self._unresolved_shadow_record("88m", index=0)])
        self._write_candles(
            [
                self._candle_at(
                    "88m",
                    timestamp="2026-05-02T00:00:00+00:00",
                    high=106.0,
                    low=99.0,
                )
            ]
        )

        payload = resolve_betrayal_shadow_outcomes(log_dir=self.log_dir)

        self.assertEqual(0, payload["newly_resolved_records"])
        self.assertEqual(1, payload["no_data_records"])
        self.assertIn("no_temporally_aligned_candles", payload["blockers"])

    def test_r81_4_valid_aligned_candles_resolve_win_and_loss_with_temporal_fields(self) -> None:
        for high, low, expected in ((106.0, 99.0, SHADOW_WIN), (101.0, 94.0, SHADOW_LOSS)):
            with self.subTest(expected=expected):
                temp_dir = tempfile.TemporaryDirectory()
                case_dir = Path(temp_dir.name)
                self._write_shadow_records_to(case_dir, [self._unresolved_shadow_record("222m", index=0)])
                self._write_candles_to(case_dir, [self._candle("222m", high=high, low=low)])

                payload = resolve_betrayal_shadow_outcomes(log_dir=case_dir)

                record = payload["records"][0]
                self.assertEqual(expected, record["shadow_status"])
                self.assertTrue(record["temporal_alignment_ok"])
                self.assertEqual("TEMPORAL_ALIGNMENT_OK", record["temporal_alignment_status"])
                self.assertEqual("2026-05-01T00:00:00+00:00", record["evaluation_window_start"])
                self.assertEqual("2026-05-01T11:06:00+00:00", record["evaluation_window_end"])
                temp_dir.cleanup()

    def test_r81_4_persisted_unsafe_resolution_is_not_counted_by_r81_validation(self) -> None:
        self._seed_group("primary-222m", "222m", "long", "ladder_close_50_618", wins=6, losses=42, total_pnl=-14.1309)
        shadow = self._unresolved_shadow_record("222m", index=0)
        shadow["signal_timestamp"] = "2026-04-29T12:00:00+00:00"
        self._write_shadow_records([shadow])
        self._write_resolutions(
            [
                self._resolution_record(
                    "222m",
                    index=0,
                    signal_timestamp="2026-04-29T12:00:00+00:00",
                    resolved_candle_timestamp="2026-05-13T12:00:00+00:00",
                )
            ]
        )

        payload = build_betrayal_inverse_validation(log_dir=self.log_dir, min_true_inverse_sample=1)
        resolutions = build_betrayal_shadow_resolutions_payload(log_dir=self.log_dir)

        primary = self._find(payload["timeframe_aggregate_validations"], timeframe="222m")
        self.assertEqual(0, primary["true_inverse_sample_count"])
        self.assertEqual(1, payload["true_inverse_summary"]["invalid_resolution_records"])
        self.assertEqual(0, payload["true_inverse_summary"]["resolved_shadow_records"])
        self.assertEqual(1, resolutions["summary"]["invalid_resolution_records"])
        self.assertFalse(resolutions["records"][0]["temporal_alignment_ok"])
        self.assertIn("resolved_candle_after_evaluation_window", resolutions["records"][0]["resolution_blockers"])

    def test_r81_4_persisted_safe_resolution_is_counted_by_r81_validation(self) -> None:
        self._seed_group("primary-222m", "222m", "long", "ladder_close_50_618", wins=6, losses=42, total_pnl=-14.1309)
        self._write_shadow_records([self._unresolved_shadow_record("222m", index=0)])
        self._write_resolutions(
            [
                self._resolution_record(
                    "222m",
                    index=0,
                    signal_timestamp="2026-05-01T00:00:00+00:00",
                    resolved_candle_timestamp="2026-05-01T00:01:00+00:00",
                )
            ]
        )

        payload = build_betrayal_inverse_validation(log_dir=self.log_dir, min_true_inverse_sample=1)

        primary = self._find(payload["timeframe_aggregate_validations"], timeframe="222m")
        self.assertEqual(1, primary["true_inverse_sample_count"])
        self.assertEqual(TRUE_INVERSE_VALIDATED_PRIMARY, primary["validation_status"])
        self.assertEqual(1, payload["true_inverse_summary"]["temporally_valid_resolved_records"])
        self.assertEqual(0, payload["true_inverse_summary"]["invalid_resolution_records"])

    def test_r81_4_api_resolutions_show_temporal_alignment_fields(self) -> None:
        self._write_resolutions(
            [
                self._resolution_record(
                    "222m",
                    index=0,
                    signal_timestamp="2026-04-29T12:00:00+00:00",
                    resolved_candle_timestamp="2026-05-13T12:00:00+00:00",
                )
            ]
        )

        response = self.client.get("/betrayal-shadow/resolutions?limit=20")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(1, payload["summary"]["invalid_resolution_records"])
        self.assertFalse(payload["records"][0]["temporal_alignment_ok"])
        self.assertEqual("TEMPORAL_ALIGNMENT_INVALID", payload["records"][0]["temporal_alignment_status"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["network_allowed"])

    def test_r81_4_cli_prints_invalid_resolution_counts(self) -> None:
        self._seed_group("primary-222m", "222m", "long", "ladder_close_50_618", wins=6, losses=42, total_pnl=-14.1309)
        shadow = self._unresolved_shadow_record("222m", index=0)
        shadow["signal_timestamp"] = "2026-04-29T12:00:00+00:00"
        self._write_shadow_records([shadow])
        self._write_resolutions(
            [
                self._resolution_record(
                    "222m",
                    index=0,
                    signal_timestamp="2026-04-29T12:00:00+00:00",
                    resolved_candle_timestamp="2026-05-13T12:00:00+00:00",
                )
            ]
        )

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
        self.assertIn("invalid_resolution_records: 1", result.stdout)
        self.assertIn("samples=0", result.stdout)

    def test_r82_regime_payload_returns_safe_fields_and_insufficient_data(self) -> None:
        self._seed_group("normal-13m", "13m", "long", "ladder_close_50_618", wins=30, losses=0, total_pnl=3.0)

        payload = build_markov_regime_gate(log_dir=self.log_dir)

        self.assertEqual("OK", payload["status"])
        self.assertEqual("R82", payload["phase"])
        self.assertEqual("MARKOV_REGIME_GATE_ONLY_NO_ORDER", payload["execution_mode"])
        self.assertEqual(INSUFFICIENT_DATA, payload["regime_summary"]["13m"]["current_regime"])
        gate = self._find(payload["normal_candidate_regime_gates"], timeframe="13m")
        self.assertEqual(REGIME_PENDING_MORE_CANDLES, gate["gate_status"])
        self.assertFalse(payload["live_execution_enabled"])
        self.assertFalse(payload["allow_live_orders"])
        self.assertTrue(payload["global_kill_switch"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["execution_attempted"])
        self.assertFalse(payload["order_payload_created"])
        self.assertFalse(payload["network_allowed"])
        self.assertFalse(payload["secrets_shown"])

    def test_r82_bullish_candles_support_long_normal_candidate(self) -> None:
        self._seed_group("normal-13m", "13m", "long", "ladder_close_50_618", wins=30, losses=0, total_pnl=3.0)
        self._capture_close_series("13m", [100, 101, 102, 103, 104, 105])

        payload = build_markov_regime_gate(log_dir=self.log_dir)

        gate = self._find(payload["normal_candidate_regime_gates"], timeframe="13m", direction="long")
        self.assertEqual(BULL_TREND, gate["current_regime"])
        self.assertEqual(REGIME_SUPPORTS_CANDIDATE, gate["gate_status"])

    def test_r82_bearish_candles_reject_long_and_support_short_context(self) -> None:
        self._seed_group("normal-13m-long", "13m", "long", "ladder_close_50_618", wins=30, losses=0, total_pnl=3.0)
        self._seed_group("normal-13m-short", "13m", "short", "ladder_close_50_618", wins=30, losses=0, total_pnl=3.0)
        self._capture_close_series("13m", [105, 104, 103, 102, 101, 100])

        payload = build_markov_regime_gate(log_dir=self.log_dir)

        long_gate = self._find(payload["normal_candidate_regime_gates"], timeframe="13m", direction="long")
        short_gate = self._find(payload["normal_candidate_regime_gates"], timeframe="13m", direction="short")
        self.assertEqual(BEAR_TREND, long_gate["current_regime"])
        self.assertEqual(REGIME_REJECTS_CANDIDATE, long_gate["gate_status"])
        self.assertEqual(REGIME_SUPPORTS_CANDIDATE, short_gate["gate_status"])

    def test_r82_range_and_high_volatility_regimes_are_classified(self) -> None:
        self._capture_close_series("44m", [100, 100.1, 99.9, 100.05, 99.95, 100.0], range_width=0.7)
        self._capture_close_series("55m", [100, 108, 94, 112, 90, 116], range_width=6.0)

        range_payload = classify_markov_regime(symbol="BTCUSDT", timeframe="44m", log_dir=self.log_dir)
        high_vol_payload = classify_markov_regime(symbol="BTCUSDT", timeframe="55m", log_dir=self.log_dir)

        self.assertIn(range_payload["current_regime"], {RANGE, LOW_VOLATILITY})
        self.assertEqual(HIGH_VOLATILITY, high_vol_payload["current_regime"])

    def test_r82_transition_summary_is_deterministic(self) -> None:
        self._capture_close_series("13m", [100, 101, 102, 101.8, 102.4, 103.2])

        first = classify_markov_regime(symbol="BTCUSDT", timeframe="13m", log_dir=self.log_dir)
        second = classify_markov_regime(symbol="BTCUSDT", timeframe="13m", log_dir=self.log_dir)

        self.assertEqual(first["transition_summary"], second["transition_summary"])
        self.assertIn("matrix", first["transition_summary"])

    def test_r82_betrayal_aggregate_candidates_are_gated_without_live_readiness(self) -> None:
        self._seed_group("primary-222m", "222m", "long", "ladder_close_50_618", wins=6, losses=42, total_pnl=-14.1309)
        self._seed_group("watch-88m", "88m", "long", "ladder_close_50_618", wins=33, losses=57, total_pnl=-1.5995)
        self._seed_group("watch-55m", "55m", "long", "ladder_close_50_618", wins=33, losses=57, total_pnl=-1.5995)
        self._write_shadow_records(
            [
                self._unresolved_shadow_record("222m", index=0),
                self._unresolved_shadow_record("88m", index=1),
                self._unresolved_shadow_record("55m", index=2),
            ]
        )
        for timeframe in ("222m", "88m", "55m"):
            self._capture_close_series(timeframe, [100, 101, 102, 103, 104, 105])

        payload = build_markov_regime_gate(log_dir=self.log_dir)

        gate_222 = self._find(payload["aggregate_candidate_regime_gates"], timeframe="222m")
        gate_88 = self._find(payload["aggregate_candidate_regime_gates"], timeframe="88m")
        gate_55 = self._find(payload["aggregate_candidate_regime_gates"], timeframe="55m")
        self.assertEqual(BETRAYAL_PRIMARY_CANDIDATE, gate_222["source_recommendation"])
        self.assertEqual(BETRAYAL_WATCHLIST, gate_88["source_recommendation"])
        self.assertEqual(BETRAYAL_WATCHLIST, gate_55["source_recommendation"])
        for gate in (gate_222, gate_88, gate_55):
            self.assertEqual(REGIME_NEUTRAL_OR_INSUFFICIENT_DATA, gate["gate_status"])
            self.assertIn("true_inverse_validation_pending", gate["blockers"])
            self.assertIn("aggregate_betrayal_direction_context_only", gate["blockers"])
            self.assertFalse(gate["order_placed"])
            self.assertFalse(gate["real_order_placed"])

    def test_r82_api_endpoint_is_safe(self) -> None:
        self._seed_group("normal-13m", "13m", "long", "ladder_close_50_618", wins=30, losses=0, total_pnl=3.0)
        self._capture_close_series("13m", [100, 101, 102, 103, 104, 105])

        response = self.client.get("/strategy-performance/markov-regime-gate")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("R82", payload["phase"])
        self.assertEqual(BULL_TREND, payload["regime_summary"]["13m"]["current_regime"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["network_allowed"])
        self.assertFalse(payload["secrets_shown"])

    def test_r82_cli_command_exists(self) -> None:
        self._seed_group("normal-13m", "13m", "long", "ladder_close_50_618", wins=30, losses=0, total_pnl=3.0)
        self._capture_close_series("13m", [100, 101, 102, 103, 104, 105])

        result = run(
            [
                ".venv/bin/python",
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                str(self.log_dir),
                "markov-regime-gate",
            ],
            cwd=Path(__file__).resolve().parents[2],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(0, result.returncode, msg=result.stderr)
        self.assertIn("R82 Markov Regime Gate: OK", result.stdout)
        self.assertIn("NORMAL CANDIDATE GATES", result.stdout)
        self.assertIn("BETRAYAL CANDIDATE GATES", result.stdout)
        self.assertIn("No order placed", result.stdout)

    def test_r83_payload_safety_fields_and_deterministic_votes(self) -> None:
        self._seed_group("normal-13m", "13m", "long", "ladder_close_50_618", wins=30, losses=0, total_pnl=3.0)
        self._capture_close_series("13m", [100, 101, 102, 103, 104, 105])

        first = build_miro_fish_quality_gate(log_dir=self.log_dir)
        second = build_miro_fish_quality_gate(log_dir=self.log_dir)

        first_gate = self._find(first["normal_candidate_quality_gates"], timeframe="13m", direction="long")
        second_gate = self._find(second["normal_candidate_quality_gates"], timeframe="13m", direction="long")
        self.assertEqual("OK", first["status"])
        self.assertEqual("R83", first["phase"])
        self.assertEqual("MIRO_FISH_QUALITY_GATE_ONLY_NO_ORDER", first["execution_mode"])
        self.assertEqual(first_gate["fish_votes"], second_gate["fish_votes"])
        self.assertFalse(first["live_execution_enabled"])
        self.assertFalse(first["allow_live_orders"])
        self.assertTrue(first["global_kill_switch"])
        self.assertFalse(first["order_placed"])
        self.assertFalse(first["real_order_placed"])
        self.assertFalse(first["execution_attempted"])
        self.assertFalse(first["order_payload_created"])
        self.assertFalse(first["network_allowed"])
        self.assertFalse(first["secrets_shown"])

    def test_r83_normal_13m_long_can_receive_support_under_bullish_regime(self) -> None:
        self._seed_group("normal-13m", "13m", "long", "ladder_close_50_618", wins=30, losses=0, total_pnl=3.0)
        self._capture_close_series("13m", [100, 101, 102, 103, 104, 105])

        payload = build_miro_fish_quality_gate(log_dir=self.log_dir)

        gate = self._find(payload["normal_candidate_quality_gates"], timeframe="13m", direction="long")
        self.assertEqual(MIRO_FISH_SUPPORTS_CANDIDATE, gate["final_quality_status"])
        self.assertIn(gate, payload["top_supported_candidates"])
        self.assertEqual(FISH_PASS, self._fish_vote(gate, "Evidence Fish")["vote_status"])
        self.assertEqual(FISH_PASS, self._fish_vote(gate, "Regime Fish")["vote_status"])

    def test_r83_normal_13m_short_is_rejected_under_bullish_regime(self) -> None:
        self._seed_group("normal-13m-short", "13m", "short", "ladder_close_50_618", wins=30, losses=0, total_pnl=3.0)
        self._capture_close_series("13m", [100, 101, 102, 103, 104, 105])

        payload = build_miro_fish_quality_gate(log_dir=self.log_dir)

        gate = self._find(payload["normal_candidate_quality_gates"], timeframe="13m", direction="short")
        self.assertEqual(MIRO_FISH_REJECTS_CANDIDATE, gate["final_quality_status"])
        self.assertEqual("REGIME_REJECTS_CANDIDATE", gate["markov_gate_status"])
        self.assertIn("regime_rejects_candidate", gate["blockers"])

    def test_r83_44m_long_insufficient_source_is_not_strongly_supported(self) -> None:
        self._seed_group("normal-44m", "44m", "long", "ladder_close_50_618", wins=2, losses=0, total_pnl=2.0)
        self._capture_close_series("44m", [100, 101, 102, 103, 104, 105])

        payload = build_miro_fish_quality_gate(log_dir=self.log_dir)

        gate = self._find(payload["normal_candidate_quality_gates"], timeframe="44m", direction="long")
        self.assertEqual(MIRO_FISH_NEEDS_MORE_EVIDENCE, gate["final_quality_status"])
        self.assertIn("source_evidence_insufficient", gate["blockers"])

    def test_r83_betrayal_aggregates_are_blocked_while_true_inverse_pending(self) -> None:
        self._seed_group("primary-222m", "222m", "long", "ladder_close_50_618", wins=6, losses=42, total_pnl=-14.1309)
        self._seed_group("watch-88m", "88m", "long", "ladder_close_50_618", wins=33, losses=57, total_pnl=-1.5995)
        self._seed_group("watch-55m", "55m", "long", "ladder_close_50_618", wins=33, losses=57, total_pnl=-1.5995)
        self._write_shadow_records(
            [
                self._unresolved_shadow_record("222m", index=0),
                self._unresolved_shadow_record("88m", index=1),
                self._unresolved_shadow_record("55m", index=2),
            ]
        )
        for timeframe in ("222m", "88m", "55m"):
            self._capture_close_series(timeframe, [100, 101, 102, 103, 104, 105])

        payload = build_miro_fish_quality_gate(log_dir=self.log_dir)

        for timeframe in ("222m", "88m", "55m"):
            gate = self._find(payload["betrayal_candidate_quality_gates"], timeframe=timeframe, audit_scope="timeframe_aggregate")
            self.assertEqual(MIRO_FISH_BLOCKED, gate["final_quality_status"])
            self.assertEqual(FISH_BLOCKED, self._fish_vote(gate, "Betrayal Fish")["vote_status"])
            self.assertIn("true_inverse_validation_pending", gate["blockers"])
            self.assertIn("aggregate_betrayal_direction_context_only", gate["blockers"])

    def test_r83_direction_entry_mode_betrayal_cannot_bypass_true_inverse_pending(self) -> None:
        self._seed_group("direction-4m", "4m", "long", "fib_618", wins=6, losses=42, total_pnl=-14.1309)
        self._write_shadow_records([self._unresolved_shadow_record("4m", index=0)])
        self._capture_close_series("4m", [100, 99, 98, 97, 96, 95])

        payload = build_miro_fish_quality_gate(log_dir=self.log_dir)

        gate = self._find(payload["betrayal_candidate_quality_gates"], timeframe="4m", audit_scope="direction_entry_mode")
        self.assertEqual(MIRO_FISH_BLOCKED, gate["final_quality_status"])
        self.assertIn("true_inverse_validation_pending", gate["blockers"])

    def test_r83_invalid_persisted_resolution_blocks_data_integrity_fish(self) -> None:
        self._seed_group("normal-13m", "13m", "long", "ladder_close_50_618", wins=30, losses=0, total_pnl=3.0)
        self._capture_close_series("13m", [100, 101, 102, 103, 104, 105])
        self._write_resolutions(
            [
                self._resolution_record(
                    "222m",
                    index=0,
                    signal_timestamp="2026-04-29T12:00:00+00:00",
                    resolved_candle_timestamp="2026-05-13T12:00:00+00:00",
                )
            ]
        )

        payload = build_miro_fish_quality_gate(log_dir=self.log_dir)

        gate = self._find(payload["normal_candidate_quality_gates"], timeframe="13m", direction="long")
        self.assertEqual(MIRO_FISH_BLOCKED, gate["final_quality_status"])
        self.assertEqual(FISH_BLOCKED, self._fish_vote(gate, "Data Integrity Fish")["vote_status"])
        self.assertIn("invalid_resolution_records_present", gate["blockers"])

    def test_r83_api_endpoint_is_safe(self) -> None:
        self._seed_group("normal-13m", "13m", "long", "ladder_close_50_618", wins=30, losses=0, total_pnl=3.0)
        self._capture_close_series("13m", [100, 101, 102, 103, 104, 105])

        response = self.client.get("/strategy-performance/miro-fish-quality-gate")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("R83", payload["phase"])
        self.assertGreaterEqual(len(payload["normal_candidate_quality_gates"]), 1)
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["network_allowed"])
        self.assertFalse(payload["secrets_shown"])

    def test_r83_cli_command_exists(self) -> None:
        self._seed_group("normal-13m", "13m", "long", "ladder_close_50_618", wins=30, losses=0, total_pnl=3.0)
        self._capture_close_series("13m", [100, 101, 102, 103, 104, 105])

        result = run(
            [
                ".venv/bin/python",
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                str(self.log_dir),
                "miro-fish-quality-gate",
            ],
            cwd=Path(__file__).resolve().parents[2],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(0, result.returncode, msg=result.stderr)
        self.assertIn("R83 Miro Fish Quality Gate: OK", result.stdout)
        self.assertIn("COMMITTEE SUMMARY", result.stdout)
        self.assertIn("TOP SUPPORTED CANDIDATES", result.stdout)
        self.assertIn("No order placed", result.stdout)

    def test_r84_payload_safety_fields_and_top_candidate_selected(self) -> None:
        self._seed_supported_13m_long()

        payload = build_live_arming_preflight(log_dir=self.log_dir)

        self.assertEqual("OK", payload["status"])
        self.assertEqual("R84", payload["phase"])
        self.assertEqual("LIVE_ARMING_PREFLIGHT_ONLY_NO_ORDER", payload["execution_mode"])
        self.assertEqual("normal|BTCUSDT|13m|long|ladder_close_50_618", payload["top_candidate_preflight"]["candidate_id"])
        self.assertEqual("MIRO_FISH_SUPPORTS_CANDIDATE", payload["top_candidate_preflight"]["miro_fish_status"])
        self.assertEqual(BLOCKED_BY_MISSING_OPERATOR_APPROVAL, payload["final_preflight_status"])
        self.assertEqual("RISK_CONTRACT_VALID_FOR_PREFLIGHT", payload["risk_contract"]["risk_contract_status"])
        self.assertEqual("FUNDING_CONFIG_PRESENT", payload["funding_preflight"]["funding_status"])
        self.assertFalse(payload["live_execution_enabled"])
        self.assertFalse(payload["allow_live_orders"])
        self.assertTrue(payload["global_kill_switch"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["execution_attempted"])
        self.assertFalse(payload["order_payload_created"])
        self.assertFalse(payload["network_allowed"])
        self.assertFalse(payload["secrets_shown"])

    def test_r84_candidate_without_miro_support_is_not_selected(self) -> None:
        self._seed_group("normal-13m-short", "13m", "short", "ladder_close_50_618", wins=30, losses=0, total_pnl=3.0)
        self._capture_close_series("13m", [100, 101, 102, 103, 104, 105])

        payload = build_live_arming_preflight(
            log_dir=self.log_dir,
            candidate_id="normal|BTCUSDT|13m|short|ladder_close_50_618",
        )

        self.assertEqual(BLOCKED_BY_STRATEGY_QUALITY, payload["final_preflight_status"])
        self.assertIsNone(payload["top_candidate_preflight"]["candidate_id"])

    def test_r84_1_default_config_removes_missing_risk_contract_blocker(self) -> None:
        self._seed_supported_13m_long()

        payload = build_live_arming_preflight(log_dir=self.log_dir)

        self.assertEqual(BLOCKED_BY_MISSING_OPERATOR_APPROVAL, payload["final_preflight_status"])
        self.assertEqual("RISK_CONTRACT_VALID_FOR_PREFLIGHT", payload["risk_contract"]["risk_contract_status"])
        self.assertNotIn("missing_stop_price_or_stop_distance_pct", payload["risk_contract"]["blockers"])
        self.assertFalse(payload["order_payload_created"])

    def test_r84_valid_local_risk_contract_blocks_on_missing_operator_approval(self) -> None:
        self._seed_supported_13m_long()

        payload = build_live_arming_preflight(log_dir=self.log_dir, env=self._r84_ready_env())

        self.assertEqual(BLOCKED_BY_MISSING_OPERATOR_APPROVAL, payload["final_preflight_status"])
        self.assertEqual("RISK_CONTRACT_VALID_FOR_PREFLIGHT", payload["risk_contract"]["risk_contract_status"])
        self.assertEqual("FUNDING_CONFIG_PRESENT", payload["funding_preflight"]["funding_status"])
        self.assertEqual("LIVE_ENV_LOCKED_SAFE_FOR_PREFLIGHT", payload["live_env_preflight"]["live_env_status"])
        self.assertEqual("MISSING_OPERATOR_APPROVAL", payload["operator_approval_preflight"]["approval_status"])
        self.assertFalse(payload["order_payload_created"])
        self.assertFalse(payload["execution_attempted"])

    def test_r84_1_local_funding_config_is_recognized_without_network(self) -> None:
        self._seed_supported_13m_long()
        env = self._r84_ready_env()
        env["HAMMER_R84_FUNDING_CONFIG_PRESENT"] = "false"

        payload = build_live_arming_preflight(log_dir=self.log_dir, env=env)

        self.assertEqual(BLOCKED_BY_MISSING_OPERATOR_APPROVAL, payload["final_preflight_status"])
        self.assertEqual("FUNDING_CONFIG_PRESENT", payload["funding_preflight"]["funding_status"])
        self.assertEqual("LOCAL_CONFIG_ONLY_NO_NETWORK", payload["funding_preflight"]["funding_check_mode"])
        self.assertNotIn("funding_config_missing", payload["funding_preflight"]["blockers"])
        self.assertFalse(payload["network_allowed"])

    def test_r84_live_env_disabled_and_kill_switch_reported_safe_for_review(self) -> None:
        self._seed_supported_13m_long()

        payload = build_live_arming_preflight(log_dir=self.log_dir, env=self._r84_ready_env())

        live_env = payload["live_env_preflight"]
        self.assertFalse(live_env["configured_live_execution_enabled"])
        self.assertFalse(live_env["configured_allow_live_orders"])
        self.assertTrue(live_env["configured_global_kill_switch"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])

    def test_r84_betrayal_candidate_id_remains_out_of_arming_path(self) -> None:
        self._seed_group("primary-222m", "222m", "long", "ladder_close_50_618", wins=6, losses=42, total_pnl=-14.1309)
        self._write_shadow_records([self._unresolved_shadow_record("222m", index=0)])
        self._capture_close_series("222m", [100, 101, 102, 103, 104, 105])

        payload = build_live_arming_preflight(
            log_dir=self.log_dir,
            candidate_id="betrayal|aggregate|BTCUSDT|222m",
            env=self._r84_ready_env(),
        )

        self.assertEqual(BLOCKED_BY_STRATEGY_QUALITY, payload["final_preflight_status"])
        self.assertIn("no_miro_fish_supported_candidate", payload["risk_contract"]["blockers"])

    def test_r84_api_endpoint_is_read_only_and_safe(self) -> None:
        self._seed_supported_13m_long()

        response = self.client.get("/live-arming/preflight")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("R84", payload["phase"])
        self.assertEqual(BLOCKED_BY_MISSING_OPERATOR_APPROVAL, payload["final_preflight_status"])
        self.assertEqual("RISK_CONTRACT_VALID_FOR_PREFLIGHT", payload["risk_contract"]["risk_contract_status"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["order_payload_created"])
        self.assertFalse(payload["network_allowed"])
        self.assertFalse(payload["secrets_shown"])

    def test_r84_cli_command_exists(self) -> None:
        self._seed_supported_13m_long()

        result = run(
            [
                ".venv/bin/python",
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                str(self.log_dir),
                "live-arming-preflight",
            ],
            cwd=Path(__file__).resolve().parents[2],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(0, result.returncode, msg=result.stderr)
        self.assertIn("R84 Live Arming Preflight: OK", result.stdout)
        self.assertIn("risk_contract_status:", result.stdout)
        self.assertIn("final_preflight_status:", result.stdout)
        self.assertIn("No order placed", result.stdout)

    def test_r84_1_risk_contract_config_loads_and_validates(self) -> None:
        payload = build_tiny_live_risk_contract_payload()

        self.assertEqual("OK", payload["status"])
        self.assertEqual("R84.1", payload["phase"])
        self.assertEqual("TINY_LIVE_RISK_CONTRACT_CONFIG_ONLY_NO_ORDER", payload["execution_mode"])
        self.assertEqual("normal|BTCUSDT|13m|long|ladder_close_50_618", payload["candidate_id"])
        self.assertEqual(RISK_CONTRACT_VALID_FOR_PREFLIGHT, payload["validation"]["validation_status"])
        self.assertEqual("LOCAL_CONFIG_ONLY_NO_NETWORK", payload["funding_config"]["funding_check_mode"])
        self.assertFalse(payload["order_payload_created"])
        self.assertFalse(payload["network_allowed"])
        self.assertFalse(payload["secrets_shown"])

    def test_r84_1_risk_contract_rejects_mismatched_candidate(self) -> None:
        payload = build_tiny_live_risk_contract_payload(candidate_id="normal|BTCUSDT|13m|short|ladder_close_50_618")

        self.assertEqual("RISK_CONTRACT_NOT_FOUND", payload["validation"]["validation_status"])
        self.assertIn("risk_contract_not_found", payload["validation"]["blockers"])

    def test_r84_1_missing_stop_or_take_profit_blocks(self) -> None:
        contract = self._valid_r84_contract()
        contract.pop("stop_distance_pct")
        contract.pop("take_profit_distance_pct")

        validation = validate_risk_contract(contract, candidate_id=contract["candidate_id"])

        self.assertEqual(RISK_CONTRACT_INVALID, validation["validation_status"])
        self.assertIn("missing_stop_price_or_stop_distance_pct", validation["blockers"])
        self.assertIn("missing_take_profit_price_or_take_profit_distance_pct", validation["blockers"])

    def test_r84_1_caps_leverage_and_margin_mode_are_validated(self) -> None:
        cases = (
            ("max_margin_usdt", 45.0, "max_margin_usdt outside tiny-live cap"),
            ("max_loss_usdt", 5.0, "max_loss_usdt outside tiny-live cap"),
            ("leverage", None, "leverage missing or unsafe"),
            ("margin_mode", "CROSSED", "margin_mode must be ISOLATED_REQUIRED"),
        )
        for key, value, blocker in cases:
            with self.subTest(key=key):
                contract = self._valid_r84_contract()
                contract[key] = value

                validation = validate_risk_contract(contract, candidate_id=contract["candidate_id"])

                self.assertEqual(RISK_CONTRACT_INVALID, validation["validation_status"])
                self.assertIn(blocker, validation["blockers"])

    def test_r84_1_preflight_uses_config_and_blocks_only_missing_operator_approval(self) -> None:
        self._seed_supported_13m_long()

        payload = build_live_arming_preflight(log_dir=self.log_dir)

        self.assertEqual(BLOCKED_BY_MISSING_OPERATOR_APPROVAL, payload["final_preflight_status"])
        self.assertEqual("RISK_CONTRACT_VALID_FOR_PREFLIGHT", payload["risk_contract"]["risk_contract_status"])
        self.assertTrue(payload["risk_contract"]["risk_contract_loaded"])
        self.assertEqual("FUNDING_CONFIG_PRESENT", payload["funding_preflight"]["funding_status"])
        self.assertEqual("MISSING_OPERATOR_APPROVAL", payload["operator_approval_preflight"]["approval_status"])
        self.assertIn("missing_operator_approval", payload["blockers"])
        self.assertFalse(payload["order_payload_created"])
        self.assertFalse(payload["network_allowed"])

    def test_r84_1_api_endpoint_is_safe(self) -> None:
        response = self.client.get("/live-arming/risk-contract")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("R84.1", payload["phase"])
        self.assertEqual(RISK_CONTRACT_VALID_FOR_PREFLIGHT, payload["validation"]["validation_status"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["order_payload_created"])
        self.assertFalse(payload["network_allowed"])

    def test_r84_1_cli_command_exists(self) -> None:
        result = run(
            [
                ".venv/bin/python",
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                str(self.log_dir),
                "tiny-live-risk-contract",
            ],
            cwd=Path(__file__).resolve().parents[2],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(0, result.returncode, msg=result.stderr)
        self.assertIn("R84.1 Tiny Live Risk Contract: OK", result.stdout)
        self.assertIn("validation_status: RISK_CONTRACT_VALID_FOR_PREFLIGHT", result.stdout)
        self.assertIn("No order placed", result.stdout)

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
        return BetrayalStrategyAuditTestCase._candle_at(
            timeframe,
            timestamp="2026-05-01T00:01:00+00:00",
            high=high,
            low=low,
        )

    @staticmethod
    def _candle_at(timeframe: str, *, timestamp: str, high: float, low: float) -> dict:
        return {
            "symbol": "BTCUSDT",
            "timeframe": timeframe,
            "timestamp": timestamp,
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

    def _write_resolutions(self, records: list[dict]) -> None:
        path = self.log_dir / RESOLUTIONS_FILENAME
        with path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, sort_keys=True) + "\n")

    def _capture_close_series(self, timeframe: str, closes: list[float], *, range_width: float = 0.2) -> None:
        base_time = datetime(2026, 5, 1, tzinfo=UTC)
        candles = []
        for index, close in enumerate(closes):
            candles.append(
                {
                    "symbol": "BTCUSDT",
                    "timeframe": timeframe,
                    "timestamp": (base_time + timedelta(minutes=index)).isoformat(),
                    "open_time": (base_time + timedelta(minutes=index)).isoformat(),
                    "open": close,
                    "high": close + range_width,
                    "low": close - range_width,
                    "close": close,
                    "volume": 1.0,
                }
            )
        capture_candles(candles, log_dir=self.log_dir)

    def _seed_supported_13m_long(self) -> None:
        self._seed_group("normal-13m", "13m", "long", "ladder_close_50_618", wins=30, losses=0, total_pnl=3.0)
        self._capture_close_series("13m", [100, 101, 102, 103, 104, 105])

    @staticmethod
    def _r84_ready_env() -> dict[str, str]:
        return {
            "HAMMER_R84_STOP_DISTANCE_PCT": "1.0",
            "HAMMER_R84_TAKE_PROFIT_DISTANCE_PCT": "2.0",
            "HAMMER_R84_MAX_POSITION_NOTIONAL_USDT": "44",
            "HAMMER_R84_MAX_MARGIN_USDT": "44",
            "HAMMER_R84_MAX_LOSS_USDT": "4.44",
            "HAMMER_R84_LEVERAGE": "1",
            "HAMMER_R84_MARGIN_MODE": "ISOLATED",
            "HAMMER_R84_FUNDING_CONFIG_PRESENT": "true",
            "HAMMER_BINANCE_LIVE_ENABLED": "false",
            "HAMMER_LIVE_EXECUTION_ENABLED": "false",
            "HAMMER_ALLOW_LIVE_ORDERS": "false",
            "HAMMER_GLOBAL_KILL_SWITCH": "true",
        }

    @staticmethod
    def _valid_r84_contract() -> dict:
        return {
            "candidate_id": "normal|BTCUSDT|13m|long|ladder_close_50_618",
            "symbol": "BTCUSDT",
            "timeframe": "13m",
            "direction": "long",
            "entry_mode": "ladder_close_50_618",
            "enabled_for_preflight": True,
            "entry_price_source": "operator_supplied_or_future_ticket_builder",
            "stop_distance_pct": 0.35,
            "take_profit_distance_pct": 0.7,
            "risk_reward_ratio": 2.0,
            "max_position_notional_usdt": 44.0,
            "max_margin_usdt": 44.0,
            "max_loss_usdt": 4.44,
            "leverage": 1,
            "margin_mode": "ISOLATED_REQUIRED",
            "reduce_only_allowed": True,
            "protective_stop_required": True,
            "take_profit_required": True,
            "order_type": "not_created",
        }

    @staticmethod
    def _fish_vote(gate: dict, fish: str) -> dict:
        for vote in gate["fish_votes"]:
            if vote["fish"] == fish:
                return vote
        raise AssertionError(f"fish vote not found: {fish}")

    @staticmethod
    def _resolution_record(
        timeframe: str,
        *,
        index: int,
        signal_timestamp: str,
        resolved_candle_timestamp: str,
        status: str = SHADOW_WIN,
        pnl_pct: float = 5.0,
    ) -> dict:
        return {
            "shadow_outcome_id": f"shadow-{timeframe}-{index}",
            "created_at": signal_timestamp,
            "resolver_phase": "R81.1",
            "resolver_source": "test",
            "original_signal_id": f"signal-{timeframe}-{index}",
            "original_direction": "short",
            "shadow_direction": "long",
            "symbol": "BTCUSDT",
            "timeframe": timeframe,
            "signal_timestamp": signal_timestamp,
            "resolved_at": resolved_candle_timestamp,
            "resolved_candle_timestamp": resolved_candle_timestamp,
            "resolution_status": status,
            "shadow_status": status,
            "shadow_entry": 100.0,
            "shadow_stop": 95.0,
            "shadow_take_profit": 105.0,
            "shadow_exit_price": 105.0 if status == SHADOW_WIN else 95.0,
            "shadow_close_reason": "take_profit" if status == SHADOW_WIN else "stop",
            "shadow_pnl_pct": pnl_pct,
            "true_inverse_pnl_pct": pnl_pct,
            "comparison": {"shadow_better": status == SHADOW_WIN, "original_better": status == SHADOW_LOSS},
            "live_execution_enabled": False,
            "order_placed": False,
            "shadow_only": True,
        }


if __name__ == "__main__":
    unittest.main()
