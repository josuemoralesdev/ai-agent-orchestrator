from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from subprocess import run
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.paper_refresh_scheduler import (
    AVAILABLE_TASKS,
    DEFAULT_TASKS,
    TASK_FINAL_HUMAN_REVIEW_PACKET,
    TASK_HUMAN_CONFIRMATION_RECORDS,
    TASK_LIVE_ARMING_PREFLIGHT,
    TASK_LIVE_ENV_ARMING_CHECKLIST,
    TASK_LIVE_ENV_BOUNDARY_REVIEW,
    TASK_MARKOV_REGIME_GATE,
    TASK_MIRO_FISH_QUALITY_GATE,
    TASK_REVIEW_RECORD_AGGREGATOR,
    TASK_CANDIDATE_REVALIDATION_WATCH,
    TASK_DUAL_LANE_CANDIDATE_WATCH,
    TASK_BETRAYAL_TRUE_PAPER_SCAFFOLD,
    TASK_BETRAYAL_PAPER_OUTCOME_LEDGER,
    TASK_SOURCE_CHAIN_REPAIR,
    TASK_SOURCE_WARNING_REVIEW,
    TASK_TINY_LIVE_RISK_CONTRACT,
    TASK_TINY_LIVE_TICKET_BUILDER,
    build_refresh_runs_payload,
    load_refresh_runs,
    run_refresh_sequence,
    scheduler_status,
)
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR


class PaperRefreshSchedulerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict(os.environ, {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=True)
        self.env_patch.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_scheduler_status_returns_safety_fields_false(self) -> None:
        status = scheduler_status(log_dir=self.log_dir)

        self.assertFalse(status["live_execution_enabled"])
        self.assertFalse(status["order_placed"])
        self.assertTrue(status["btc_live_only"])

    def test_default_task_list_includes_all_required_tasks(self) -> None:
        self.assertEqual(
            [
                "market_intelligence",
                "multi_symbol_scan",
                "eth_paper_candidate",
                "eth_paper_outcome",
                "betrayal_shadow_track",
                "notification_check",
            ],
            list(DEFAULT_TASKS),
        )
        self.assertIn(TASK_MARKOV_REGIME_GATE, AVAILABLE_TASKS)
        self.assertNotIn(TASK_MARKOV_REGIME_GATE, DEFAULT_TASKS)
        self.assertIn(TASK_MIRO_FISH_QUALITY_GATE, AVAILABLE_TASKS)
        self.assertNotIn(TASK_MIRO_FISH_QUALITY_GATE, DEFAULT_TASKS)
        self.assertIn(TASK_LIVE_ARMING_PREFLIGHT, AVAILABLE_TASKS)
        self.assertNotIn(TASK_LIVE_ARMING_PREFLIGHT, DEFAULT_TASKS)
        self.assertIn(TASK_TINY_LIVE_RISK_CONTRACT, AVAILABLE_TASKS)
        self.assertNotIn(TASK_TINY_LIVE_RISK_CONTRACT, DEFAULT_TASKS)
        self.assertIn(TASK_TINY_LIVE_TICKET_BUILDER, AVAILABLE_TASKS)
        self.assertNotIn(TASK_TINY_LIVE_TICKET_BUILDER, DEFAULT_TASKS)
        self.assertIn(TASK_LIVE_ENV_ARMING_CHECKLIST, AVAILABLE_TASKS)
        self.assertNotIn(TASK_LIVE_ENV_ARMING_CHECKLIST, DEFAULT_TASKS)
        self.assertIn(TASK_LIVE_ENV_BOUNDARY_REVIEW, AVAILABLE_TASKS)
        self.assertNotIn(TASK_LIVE_ENV_BOUNDARY_REVIEW, DEFAULT_TASKS)
        self.assertIn(TASK_FINAL_HUMAN_REVIEW_PACKET, AVAILABLE_TASKS)
        self.assertNotIn(TASK_FINAL_HUMAN_REVIEW_PACKET, DEFAULT_TASKS)
        self.assertIn(TASK_HUMAN_CONFIRMATION_RECORDS, AVAILABLE_TASKS)
        self.assertNotIn(TASK_HUMAN_CONFIRMATION_RECORDS, DEFAULT_TASKS)
        self.assertIn(TASK_REVIEW_RECORD_AGGREGATOR, AVAILABLE_TASKS)
        self.assertNotIn(TASK_REVIEW_RECORD_AGGREGATOR, DEFAULT_TASKS)
        self.assertIn(TASK_SOURCE_WARNING_REVIEW, AVAILABLE_TASKS)
        self.assertNotIn(TASK_SOURCE_WARNING_REVIEW, DEFAULT_TASKS)
        self.assertIn(TASK_SOURCE_CHAIN_REPAIR, AVAILABLE_TASKS)
        self.assertNotIn(TASK_SOURCE_CHAIN_REPAIR, DEFAULT_TASKS)
        self.assertIn(TASK_CANDIDATE_REVALIDATION_WATCH, AVAILABLE_TASKS)
        self.assertNotIn(TASK_CANDIDATE_REVALIDATION_WATCH, DEFAULT_TASKS)
        self.assertIn(TASK_DUAL_LANE_CANDIDATE_WATCH, AVAILABLE_TASKS)
        self.assertNotIn(TASK_DUAL_LANE_CANDIDATE_WATCH, DEFAULT_TASKS)
        self.assertIn(TASK_BETRAYAL_TRUE_PAPER_SCAFFOLD, AVAILABLE_TASKS)
        self.assertNotIn(TASK_BETRAYAL_TRUE_PAPER_SCAFFOLD, DEFAULT_TASKS)
        self.assertIn(TASK_BETRAYAL_PAPER_OUTCOME_LEDGER, AVAILABLE_TASKS)
        self.assertNotIn(TASK_BETRAYAL_PAPER_OUTCOME_LEDGER, DEFAULT_TASKS)

    def test_paper_refresh_run_executes_default_tasks_with_mocked_helpers(self) -> None:
        with self._mock_helpers():
            record = run_refresh_sequence(
                use_network=False,
                write_outputs=True,
                send_notifications=False,
                run_mode="CLI",
                log_dir=self.log_dir,
            )

        self.assertEqual(list(DEFAULT_TASKS), record["completed_tasks"])
        self.assertEqual([], record["failed_tasks"])
        self.assertFalse(record["live_execution_enabled"])
        self.assertFalse(record["order_placed"])

    def test_paper_refresh_run_records_ndjson(self) -> None:
        with self._mock_helpers():
            record = run_refresh_sequence(log_dir=self.log_dir, use_network=False, write_outputs=True)

        records = load_refresh_runs(limit=10, log_dir=self.log_dir)

        self.assertTrue((self.log_dir / "paper_refresh_runs.ndjson").exists())
        self.assertEqual(1, len(records))
        self.assertEqual(record["refresh_run_id"], records[0]["refresh_run_id"])

    def test_task_failures_are_captured_without_crashing_scheduler(self) -> None:
        with patch(
            "src.app.hammer_radar.operator.paper_refresh_scheduler.build_market_intelligence_summary",
            side_effect=RuntimeError("boom"),
        ), patch(
            "src.app.hammer_radar.operator.paper_refresh_scheduler.check_notifications",
            return_value=self._notification_result(),
        ):
            record = run_refresh_sequence(
                tasks=["market_intelligence", "notification_check"],
                use_network=False,
                write_outputs=False,
                send_notifications=False,
                log_dir=self.log_dir,
            )

        self.assertEqual(["notification_check"], record["completed_tasks"])
        self.assertEqual(["market_intelligence"], record["failed_tasks"])
        self.assertEqual("RuntimeError", record["task_results"]["market_intelligence"]["error_type"])

    def test_notification_task_does_not_send_fake_alert_when_not_ready(self) -> None:
        with patch(
            "src.app.hammer_radar.operator.paper_refresh_scheduler.check_notifications",
            return_value=self._notification_result(would_alert=False, send_requested=False),
        ) as mocked:
            record = run_refresh_sequence(
                tasks=["notification_check"],
                use_network=False,
                write_outputs=True,
                send_notifications=False,
                log_dir=self.log_dir,
            )

        mocked.assert_called_once()
        self.assertFalse(record["task_results"]["notification_check"]["detail"]["would_alert"])
        self.assertFalse(record["task_results"]["notification_check"]["detail"]["send_requested"])

    def test_use_network_false_default_does_not_require_network(self) -> None:
        with patch(
            "src.app.hammer_radar.operator.paper_refresh_scheduler.build_market_intelligence_summary",
            return_value={
                "market_data_status": "FALLBACK_ONLY",
                "network_used": False,
                "symbols_count": 19,
                "write": False,
            },
        ) as mocked:
            run_refresh_sequence(
                tasks=["market_intelligence"],
                use_network=False,
                write_outputs=False,
                log_dir=self.log_dir,
            )

        self.assertFalse(mocked.call_args.kwargs["use_network"])

    def test_optional_markov_regime_gate_task_is_read_only(self) -> None:
        with patch(
            "src.app.hammer_radar.operator.paper_refresh_scheduler.build_markov_regime_gate",
            return_value={
                "normal_candidate_regime_gates": [{}],
                "betrayal_candidate_regime_gates": [{}],
                "regime_summary": {"13m": {}},
                "execution_mode": "MARKOV_REGIME_GATE_ONLY_NO_ORDER",
            },
        ) as mocked:
            record = run_refresh_sequence(
                tasks=[TASK_MARKOV_REGIME_GATE],
                use_network=False,
                write_outputs=False,
                send_notifications=False,
                log_dir=self.log_dir,
            )

        mocked.assert_called_once()
        self.assertEqual([TASK_MARKOV_REGIME_GATE], record["completed_tasks"])
        self.assertEqual("MARKOV_REGIME_GATE_ONLY_NO_ORDER", record["task_results"][TASK_MARKOV_REGIME_GATE]["detail"]["execution_mode"])
        self.assertFalse(record["live_execution_enabled"])
        self.assertFalse(record["order_placed"])

    def test_optional_miro_fish_quality_gate_task_is_read_only(self) -> None:
        with patch(
            "src.app.hammer_radar.operator.paper_refresh_scheduler.build_miro_fish_quality_gate",
            return_value={
                "normal_candidate_quality_gates": [{}],
                "betrayal_candidate_quality_gates": [{}],
                "top_supported_candidates": [{}],
                "execution_mode": "MIRO_FISH_QUALITY_GATE_ONLY_NO_ORDER",
            },
        ) as mocked:
            record = run_refresh_sequence(
                tasks=[TASK_MIRO_FISH_QUALITY_GATE],
                use_network=False,
                write_outputs=False,
                send_notifications=False,
                log_dir=self.log_dir,
            )

        mocked.assert_called_once()
        self.assertEqual([TASK_MIRO_FISH_QUALITY_GATE], record["completed_tasks"])
        self.assertEqual(
            "MIRO_FISH_QUALITY_GATE_ONLY_NO_ORDER",
            record["task_results"][TASK_MIRO_FISH_QUALITY_GATE]["detail"]["execution_mode"],
        )
        self.assertFalse(record["live_execution_enabled"])
        self.assertFalse(record["order_placed"])

    def test_optional_live_arming_preflight_task_is_read_only(self) -> None:
        with patch(
            "src.app.hammer_radar.operator.paper_refresh_scheduler.build_live_arming_preflight",
            return_value={
                "final_preflight_status": "BLOCKED_BY_MISSING_RISK_CONTRACT",
                "top_candidate_preflight": {"candidate_id": "normal|BTCUSDT|13m|long|ladder_close_50_618"},
                "execution_mode": "LIVE_ARMING_PREFLIGHT_ONLY_NO_ORDER",
            },
        ) as mocked:
            record = run_refresh_sequence(
                tasks=[TASK_LIVE_ARMING_PREFLIGHT],
                use_network=False,
                write_outputs=False,
                send_notifications=False,
                log_dir=self.log_dir,
            )

        mocked.assert_called_once()
        self.assertEqual([TASK_LIVE_ARMING_PREFLIGHT], record["completed_tasks"])
        self.assertEqual(
            "LIVE_ARMING_PREFLIGHT_ONLY_NO_ORDER",
            record["task_results"][TASK_LIVE_ARMING_PREFLIGHT]["detail"]["execution_mode"],
        )
        self.assertFalse(record["live_execution_enabled"])
        self.assertFalse(record["order_placed"])

    def test_optional_tiny_live_risk_contract_task_is_read_only(self) -> None:
        with patch(
            "src.app.hammer_radar.operator.paper_refresh_scheduler.build_tiny_live_risk_contract_payload",
            return_value={
                "candidate_id": "normal|BTCUSDT|13m|long|ladder_close_50_618",
                "validation": {"validation_status": "RISK_CONTRACT_VALID_FOR_PREFLIGHT"},
                "execution_mode": "TINY_LIVE_RISK_CONTRACT_CONFIG_ONLY_NO_ORDER",
            },
        ) as mocked:
            record = run_refresh_sequence(
                tasks=[TASK_TINY_LIVE_RISK_CONTRACT],
                use_network=False,
                write_outputs=False,
                send_notifications=False,
                log_dir=self.log_dir,
            )

        mocked.assert_called_once()
        self.assertEqual([TASK_TINY_LIVE_RISK_CONTRACT], record["completed_tasks"])
        self.assertEqual(
            "TINY_LIVE_RISK_CONTRACT_CONFIG_ONLY_NO_ORDER",
            record["task_results"][TASK_TINY_LIVE_RISK_CONTRACT]["detail"]["execution_mode"],
        )
        self.assertFalse(record["live_execution_enabled"])
        self.assertFalse(record["order_placed"])

    def test_optional_tiny_live_ticket_builder_task_is_read_only(self) -> None:
        with patch(
            "src.app.hammer_radar.operator.paper_refresh_scheduler.build_tiny_live_ticket",
            return_value={
                "candidate_id": "normal|BTCUSDT|13m|long|ladder_close_50_618",
                "ticket_status": "TICKET_APPROVAL_REQUIRED",
                "operator_approval_status": "MISSING_OPERATOR_APPROVAL",
                "ticket_written": False,
                "execution_mode": "EXACT_OPERATOR_APPROVAL_NON_EXECUTABLE_TICKET_BUILDER_ONLY_NO_ORDER",
            },
        ) as mocked:
            record = run_refresh_sequence(
                tasks=[TASK_TINY_LIVE_TICKET_BUILDER],
                use_network=False,
                write_outputs=False,
                send_notifications=False,
                log_dir=self.log_dir,
            )

        mocked.assert_called_once()
        self.assertEqual([TASK_TINY_LIVE_TICKET_BUILDER], record["completed_tasks"])
        detail = record["task_results"][TASK_TINY_LIVE_TICKET_BUILDER]["detail"]
        self.assertEqual("TICKET_APPROVAL_REQUIRED", detail["ticket_status"])
        self.assertFalse(detail["ticket_written"])
        self.assertFalse(record["live_execution_enabled"])
        self.assertFalse(record["order_placed"])

    def test_optional_live_env_arming_checklist_task_is_read_only(self) -> None:
        with patch(
            "src.app.hammer_radar.operator.paper_refresh_scheduler.build_live_env_arming_checklist",
            return_value={
                "candidate_id": "normal|BTCUSDT|13m|long|ladder_close_50_618",
                "checklist_status": "CHECKLIST_BLOCKED_BY_MISSING_CONFIRMATIONS",
                "manual_funding_status": "MANUAL_FUNDING_CONFIRMATION_REQUIRED",
                "live_env_arming_status": "LIVE_ENV_ARMING_CONFIRMATION_REQUIRED",
                "checklist_written": False,
                "execution_mode": "LIVE_ENV_ARMING_CHECKLIST_MANUAL_FUNDING_CONFIRMATION_ONLY_NO_ORDER",
            },
        ) as mocked:
            record = run_refresh_sequence(
                tasks=[TASK_LIVE_ENV_ARMING_CHECKLIST],
                use_network=False,
                write_outputs=False,
                send_notifications=False,
                log_dir=self.log_dir,
            )

        mocked.assert_called_once()
        self.assertEqual([TASK_LIVE_ENV_ARMING_CHECKLIST], record["completed_tasks"])
        detail = record["task_results"][TASK_LIVE_ENV_ARMING_CHECKLIST]["detail"]
        self.assertEqual("CHECKLIST_BLOCKED_BY_MISSING_CONFIRMATIONS", detail["checklist_status"])
        self.assertFalse(detail["checklist_written"])
        self.assertFalse(record["live_execution_enabled"])
        self.assertFalse(record["order_placed"])

    def test_optional_live_env_boundary_review_task_is_read_only(self) -> None:
        with patch(
            "src.app.hammer_radar.operator.paper_refresh_scheduler.build_live_env_boundary_review",
            return_value={
                "candidate_id": "normal|BTCUSDT|13m|long|ladder_close_50_618",
                "boundary_status": "LIVE_ENV_ARMING_NOT_ALLOWED_YET",
                "source_preflight_status": "BLOCKED_BY_MISSING_OPERATOR_APPROVAL",
                "report_written": False,
                "execution_mode": "LIVE_ENV_TOGGLE_DESIGN_EXECUTION_BOUNDARY_REVIEW_ONLY_NO_ORDER",
            },
        ) as mocked:
            record = run_refresh_sequence(
                tasks=[TASK_LIVE_ENV_BOUNDARY_REVIEW],
                use_network=False,
                write_outputs=False,
                send_notifications=False,
                log_dir=self.log_dir,
            )

        mocked.assert_called_once()
        self.assertEqual([TASK_LIVE_ENV_BOUNDARY_REVIEW], record["completed_tasks"])
        detail = record["task_results"][TASK_LIVE_ENV_BOUNDARY_REVIEW]["detail"]
        self.assertEqual("LIVE_ENV_ARMING_NOT_ALLOWED_YET", detail["boundary_status"])
        self.assertFalse(detail["report_written"])
        self.assertFalse(record["live_execution_enabled"])
        self.assertFalse(record["order_placed"])

    def test_optional_final_human_review_packet_task_is_read_only(self) -> None:
        with patch(
            "src.app.hammer_radar.operator.paper_refresh_scheduler.build_final_human_review_packet",
            return_value={
                "candidate_id": "normal|BTCUSDT|13m|long|ladder_close_50_618",
                "packet_status": "REVIEW_PACKET_BLOCKED_BY_LIVE_ENV_BOUNDARY",
                "final_human_approval_status": "FINAL_HUMAN_APPROVAL_REQUIRED",
                "packet_written": False,
                "execution_mode": "FINAL_HUMAN_APPROVAL_RECORD_REVIEW_PACKET_ONLY_NO_ORDER",
            },
        ) as mocked:
            record = run_refresh_sequence(
                tasks=[TASK_FINAL_HUMAN_REVIEW_PACKET],
                use_network=False,
                write_outputs=False,
                send_notifications=False,
                log_dir=self.log_dir,
            )

        mocked.assert_called_once()
        self.assertEqual([TASK_FINAL_HUMAN_REVIEW_PACKET], record["completed_tasks"])
        detail = record["task_results"][TASK_FINAL_HUMAN_REVIEW_PACKET]["detail"]
        self.assertEqual("REVIEW_PACKET_BLOCKED_BY_LIVE_ENV_BOUNDARY", detail["packet_status"])
        self.assertFalse(detail["packet_written"])
        self.assertFalse(record["live_execution_enabled"])
        self.assertFalse(record["order_placed"])

    def test_optional_human_confirmation_records_task_is_dry_run_no_write(self) -> None:
        with patch(
            "src.app.hammer_radar.operator.paper_refresh_scheduler.build_human_confirmation_records",
            return_value={
                "candidate_id": "normal|BTCUSDT|13m|long|ladder_close_50_618",
                "unified_readiness_status": "REVIEW_RECORDS_MISSING",
                "records_written": 0,
                "r87_boundary_status": "LIVE_ENV_ARMING_NOT_ALLOWED_YET",
                "execution_mode": "HUMAN_CONFIRMATION_REVIEW_RECORD_LEDGER_ONLY_NO_ORDER",
            },
        ) as mocked:
            record = run_refresh_sequence(
                tasks=[TASK_HUMAN_CONFIRMATION_RECORDS],
                use_network=False,
                write_outputs=False,
                send_notifications=False,
                log_dir=self.log_dir,
            )

        mocked.assert_called_once()
        self.assertEqual([TASK_HUMAN_CONFIRMATION_RECORDS], record["completed_tasks"])
        detail = record["task_results"][TASK_HUMAN_CONFIRMATION_RECORDS]["detail"]
        self.assertEqual("REVIEW_RECORDS_MISSING", detail["unified_readiness_status"])
        self.assertEqual(0, detail["records_written"])
        self.assertFalse(record["live_execution_enabled"])
        self.assertFalse(record["order_placed"])

    def test_optional_review_record_aggregator_task_is_dry_run_no_write(self) -> None:
        with patch(
            "src.app.hammer_radar.operator.paper_refresh_scheduler.build_review_record_arming_snapshot",
            return_value={
                "candidate_id": "normal|BTCUSDT|13m|long|ladder_close_50_618",
                "snapshot_status": ["ARMING_SNAPSHOT_BLOCKED_BY_MISSING_REVIEW_RECORDS"],
                "readiness_class": "READY_FOR_HUMAN_RECORD_COMPLETION",
                "snapshot_written": False,
                "hash_chain_summary": {"hash_chain_consistent": True},
                "execution_mode": "REVIEW_RECORD_AGGREGATOR_ARMING_READINESS_SNAPSHOT_ONLY_NO_ORDER",
            },
        ) as mocked:
            record = run_refresh_sequence(
                tasks=[TASK_REVIEW_RECORD_AGGREGATOR],
                use_network=False,
                write_outputs=False,
                send_notifications=False,
                log_dir=self.log_dir,
            )

        mocked.assert_called_once()
        self.assertEqual([TASK_REVIEW_RECORD_AGGREGATOR], record["completed_tasks"])
        detail = record["task_results"][TASK_REVIEW_RECORD_AGGREGATOR]["detail"]
        self.assertEqual("READY_FOR_HUMAN_RECORD_COMPLETION", detail["readiness_class"])
        self.assertFalse(detail["snapshot_written"])
        self.assertTrue(detail["hash_chain_consistent"])
        self.assertFalse(record["live_execution_enabled"])
        self.assertFalse(record["order_placed"])

    def test_optional_source_warning_review_task_is_dry_run_no_write(self) -> None:
        with patch(
            "src.app.hammer_radar.operator.paper_refresh_scheduler.build_source_warning_review",
            return_value={
                "candidate_id": "normal|BTCUSDT|13m|long|ladder_close_50_618",
                "source_warning_classification": "CANDIDATE_SUPPORT_MISSING",
                "rehydrated_review_context": {"rehydration_status": "REHYDRATION_AVAILABLE_FOR_REVIEW"},
                "report_written": False,
                "execution_mode": "SOURCE_WARNING_REVIEW_CANDIDATE_SUPPORT_REHYDRATION_ONLY_NO_ORDER",
            },
        ) as mocked:
            record = run_refresh_sequence(
                tasks=[TASK_SOURCE_WARNING_REVIEW],
                use_network=False,
                write_outputs=False,
                send_notifications=False,
                log_dir=self.log_dir,
            )

        mocked.assert_called_once()
        self.assertEqual([TASK_SOURCE_WARNING_REVIEW], record["completed_tasks"])
        detail = record["task_results"][TASK_SOURCE_WARNING_REVIEW]["detail"]
        self.assertEqual("CANDIDATE_SUPPORT_MISSING", detail["source_warning_classification"])
        self.assertEqual("REHYDRATION_AVAILABLE_FOR_REVIEW", detail["rehydration_status"])
        self.assertFalse(detail["report_written"])
        self.assertFalse(record["live_execution_enabled"])
        self.assertFalse(record["order_placed"])

    def test_optional_source_chain_repair_task_is_dry_run_no_write(self) -> None:
        with patch(
            "src.app.hammer_radar.operator.paper_refresh_scheduler.build_source_chain_repair",
            return_value={
                "candidate_id": "normal|BTCUSDT|13m|long|ladder_close_50_618",
                "repair_classification": "LEGITIMATE_MARKET_REGIME_DRIFT",
                "recommended_next_phase": "R93 Current Candidate Revalidation + Markov/Miro Fish Threshold Review",
                "report_written": False,
                "execution_mode": "SOURCE_CHAIN_REPAIR_STRATEGY_PERFORMANCE_INPUTS_ONLY_NO_ORDER",
            },
        ) as mocked:
            record = run_refresh_sequence(
                tasks=[TASK_SOURCE_CHAIN_REPAIR],
                use_network=False,
                write_outputs=False,
                send_notifications=False,
                log_dir=self.log_dir,
            )

        mocked.assert_called_once()
        self.assertEqual([TASK_SOURCE_CHAIN_REPAIR], record["completed_tasks"])
        detail = record["task_results"][TASK_SOURCE_CHAIN_REPAIR]["detail"]
        self.assertEqual("LEGITIMATE_MARKET_REGIME_DRIFT", detail["repair_classification"])
        self.assertFalse(detail["report_written"])
        self.assertFalse(record["live_execution_enabled"])
        self.assertFalse(record["order_placed"])

    def test_optional_candidate_revalidation_watch_task_is_dry_run_no_write(self) -> None:
        with patch(
            "src.app.hammer_radar.operator.paper_refresh_scheduler.build_candidate_revalidation_watch",
            return_value={
                "candidate_id": "normal|BTCUSDT|13m|long|ladder_close_50_618",
                "revalidation_class": "STRATEGY_INPUTS_ACCEPTABLE_BUT_REGIME_PENDING",
                "support_restored": False,
                "next_action_recommendation": "R95 Markov Support Watch Scheduler / Candidate Revalidation Loop",
                "report_written": False,
                "execution_mode": "CURRENT_CANDIDATE_REVALIDATION_MARKOV_SUPPORT_WATCH_ONLY_NO_ORDER",
            },
        ) as mocked:
            record = run_refresh_sequence(
                tasks=[TASK_CANDIDATE_REVALIDATION_WATCH],
                use_network=False,
                write_outputs=False,
                send_notifications=False,
                log_dir=self.log_dir,
            )

        mocked.assert_called_once()
        self.assertEqual([TASK_CANDIDATE_REVALIDATION_WATCH], record["completed_tasks"])
        detail = record["task_results"][TASK_CANDIDATE_REVALIDATION_WATCH]["detail"]
        self.assertEqual("STRATEGY_INPUTS_ACCEPTABLE_BUT_REGIME_PENDING", detail["revalidation_class"])
        self.assertFalse(detail["support_restored"])
        self.assertFalse(detail["report_written"])
        self.assertFalse(record["live_execution_enabled"])
        self.assertFalse(record["order_placed"])

    def test_optional_dual_lane_candidate_watch_task_is_dry_run_no_write(self) -> None:
        with patch(
            "src.app.hammer_radar.operator.paper_refresh_scheduler.build_dual_lane_candidate_watch",
            return_value={
                "normal_candidate_id": "normal|BTCUSDT|13m|long|ladder_close_50_618",
                "overall_lane_class": "BETRAYAL_LANE_NEEDS_TRUE_PAPER",
                "next_action_recommendation": "R96 Betrayal True Paper Tracking Scaffold",
                "report_written": False,
                "execution_mode": "DUAL_LANE_CANDIDATE_WATCH_NORMAL_BETRAYAL_ONLY_NO_ORDER",
            },
        ) as mocked:
            record = run_refresh_sequence(
                tasks=[TASK_DUAL_LANE_CANDIDATE_WATCH],
                use_network=False,
                write_outputs=False,
                send_notifications=False,
                log_dir=self.log_dir,
            )

        mocked.assert_called_once()
        self.assertEqual([TASK_DUAL_LANE_CANDIDATE_WATCH], record["completed_tasks"])
        detail = record["task_results"][TASK_DUAL_LANE_CANDIDATE_WATCH]["detail"]
        self.assertEqual("BETRAYAL_LANE_NEEDS_TRUE_PAPER", detail["overall_lane_class"])
        self.assertFalse(detail["report_written"])
        self.assertFalse(record["live_execution_enabled"])
        self.assertFalse(record["order_placed"])

    def test_optional_betrayal_true_paper_scaffold_task_is_dry_run_no_write(self) -> None:
        with patch(
            "src.app.hammer_radar.operator.paper_refresh_scheduler.build_betrayal_true_paper_scaffold",
            return_value={
                "scaffold_summary": {"scaffold_candidate_count": 3},
                "next_action_recommendation": "R97 Betrayal Paper Outcome Ledger + First Tracking Loop",
                "report_written": False,
                "outcome_ledger_path": "logs/hammer_radar_forward/betrayal_true_paper_outcomes.ndjson",
                "execution_mode": "BETRAYAL_TRUE_PAPER_TRACKING_SCAFFOLD_ONLY_NO_ORDER",
            },
        ) as mocked:
            record = run_refresh_sequence(
                tasks=[TASK_BETRAYAL_TRUE_PAPER_SCAFFOLD],
                use_network=False,
                write_outputs=False,
                send_notifications=False,
                log_dir=self.log_dir,
            )

        mocked.assert_called_once()
        self.assertEqual([TASK_BETRAYAL_TRUE_PAPER_SCAFFOLD], record["completed_tasks"])
        detail = record["task_results"][TASK_BETRAYAL_TRUE_PAPER_SCAFFOLD]["detail"]
        self.assertEqual(3, detail["scaffold_candidate_count"])
        self.assertFalse(detail["report_written"])
        self.assertFalse(record["live_execution_enabled"])
        self.assertFalse(record["order_placed"])

    def test_optional_betrayal_paper_outcome_ledger_task_is_read_status_only(self) -> None:
        with patch(
            "src.app.hammer_radar.operator.paper_refresh_scheduler.build_betrayal_paper_outcome_status",
            return_value={
                "ledger_summary": {"ledger_record_count": 0, "valid_record_count": 0},
                "tracking_loop_status": "BETRAYAL_PAPER_TRACKING_LOOP_READY",
                "execution_mode": "BETRAYAL_PAPER_OUTCOME_LEDGER_ONLY_NO_ORDER",
            },
        ) as mocked:
            record = run_refresh_sequence(
                tasks=[TASK_BETRAYAL_PAPER_OUTCOME_LEDGER],
                use_network=False,
                write_outputs=False,
                send_notifications=False,
                log_dir=self.log_dir,
            )

        mocked.assert_called_once()
        self.assertEqual([TASK_BETRAYAL_PAPER_OUTCOME_LEDGER], record["completed_tasks"])
        detail = record["task_results"][TASK_BETRAYAL_PAPER_OUTCOME_LEDGER]["detail"]
        self.assertEqual(0, detail["ledger_record_count"])
        self.assertEqual("BETRAYAL_PAPER_TRACKING_LOOP_READY", detail["tracking_loop_status"])
        self.assertFalse(record["live_execution_enabled"])
        self.assertFalse(record["order_placed"])

    def test_api_paper_refresh_status_works(self) -> None:
        response = self.client.get("/paper-refresh/status")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertFalse(payload["live_execution_enabled"])
        self.assertFalse(payload["order_placed"])

    def test_api_paper_refresh_run_works(self) -> None:
        response = self.client.post(
            "/paper-refresh/run",
            json={"tasks": ["market_intelligence"], "use_network": False, "write_outputs": False},
        )

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertFalse(payload["live_execution_enabled"])
        self.assertFalse(payload["order_placed"])

    def test_api_paper_refresh_runs_works(self) -> None:
        with self._mock_helpers():
            run_refresh_sequence(tasks=["notification_check"], log_dir=self.log_dir)

        response = self.client.get("/paper-refresh/runs")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(1, len(payload["runs"]))

    def test_cli_paper_refresh_status_works(self) -> None:
        result = self._run_cli(["paper-refresh-status"])

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("HAMMER RADAR PAPER REFRESH STATUS", result.stdout)

    def test_cli_paper_refresh_run_works(self) -> None:
        result = self._run_cli(["paper-refresh-run", "--tasks", "market_intelligence", "--no-write"])

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("HAMMER RADAR PAPER REFRESH RUN", result.stdout)

    def test_cli_paper_refresh_runs_works(self) -> None:
        result = self._run_cli(["paper-refresh-runs"])

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("HAMMER RADAR PAPER REFRESH RUNS", result.stdout)

    def test_ui_contains_paper_refresh_scheduler_panel(self) -> None:
        response = self.client.get("/ui")

        self.assertEqual(200, response.status_code)
        html = response.text
        self.assertIn("Paper Refresh Scheduler", html)
        self.assertIn("Paper/watch refresh only.", html)
        self.assertIn("No ETH/alt live tickets.", html)

    def _mock_helpers(self):
        return patch.multiple(
            "src.app.hammer_radar.operator.paper_refresh_scheduler",
            build_market_intelligence_summary=lambda **_kwargs: {
                "market_data_status": "FALLBACK_ONLY",
                "network_used": False,
                "symbols_count": 19,
                "write": _kwargs.get("write"),
            },
            scan_watchlist=lambda **_kwargs: {
                "scanned_symbols": 19,
                "write": _kwargs.get("write"),
                "btc_live_only": True,
            },
            build_eth_paper_candidate=lambda **_kwargs: {
                "symbol": "ETHUSDT",
                "paper_candidate_status": "INSUFFICIENT_DATA",
                "tier": "ETH_INSUFFICIENT_DATA",
                "write": _kwargs.get("write"),
            },
            build_eth_paper_outcome=lambda **_kwargs: {
                "symbol": "ETHUSDT",
                "outcome_status": "ETH_PAPER_NO_DATA",
                "outcome_created": False,
                "write": _kwargs.get("write"),
            },
            track_betrayal_shadow_outcomes=lambda **_kwargs: {
                "created": 0,
                "updated": 0,
                "candidate_count": 0,
                "shadow_only": True,
            },
            check_notifications=lambda **_kwargs: self._notification_result(
                send_requested=_kwargs.get("send", False)
            ),
        )

    def _notification_result(self, *, would_alert: bool = False, send_requested: bool = False) -> dict:
        return {
            "send_requested": send_requested,
            "would_alert": would_alert,
            "recorded": False,
            "telegram": {"sent": False, "status": "not_requested"},
            "secrets_shown": False,
            "live_execution_enabled": False,
            "order_placed": False,
        }

    def _run_cli(self, args: list[str]):
        return run(
            [".venv/bin/python", "-m", "src.app.hammer_radar.operator.inspect", "--log-dir", str(self.log_dir), *args],
            cwd=Path(__file__).resolve().parents[2],
            check=False,
            capture_output=True,
            text=True,
            env={LOG_DIR_ENV_VAR: str(self.log_dir), "PATH": os.environ.get("PATH", "")},
        )


if __name__ == "__main__":
    unittest.main()
