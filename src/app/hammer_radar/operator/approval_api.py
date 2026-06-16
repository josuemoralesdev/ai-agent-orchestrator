"""Local approval-intent API for Hammer Radar operator candidates.

This module records human intent only. It does not place orders, import exchange
clients, or enable live execution.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from src.app.hammer_radar.execution.binance_futures_connector import (
    build_connector_status,
    build_protective_status,
    connector_attempts_path,
    execute_live_order,
    load_connector_attempts,
    load_protective_attempts,
    preview_payload,
    protective_attempts_path,
    protective_preview,
    submit_protective_test,
    submit_test_order,
)
from src.app.hammer_radar.operator.alt_watchlist import build_watchlist, build_watchlist_summary
from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.binance_readonly import (
    build_binance_exchange_info,
    build_binance_readonly_status,
)
from src.app.hammer_radar.operator.binance_account_read_env_contract import (
    build_binance_account_read_env_discovery,
)
from src.app.hammer_radar.operator.binance_live_status import build_binance_live_status
from src.app.hammer_radar.operator.betrayal_shadow_outcomes import (
    build_betrayal_shadow_outcomes_payload,
    track_betrayal_shadow_outcomes,
)
from src.app.hammer_radar.operator.betrayal_inverse_validation import build_betrayal_inverse_validation
from src.app.hammer_radar.operator.betrayal_candle_archive import (
    build_betrayal_candle_archive,
    build_betrayal_candle_archive_status,
)
from src.app.hammer_radar.operator.betrayal_candle_capture import (
    SOURCE_MODE_LOCAL_ONLY,
    backfill_betrayal_candle_capture,
    build_betrayal_candle_capture_status,
)
from src.app.hammer_radar.operator.betrayal_shadow_resolver import (
    build_betrayal_shadow_resolutions_payload,
    resolve_betrayal_shadow_outcomes,
)
from src.app.hammer_radar.operator.betrayal_strategy_audit import build_betrayal_strategy_audit
from src.app.hammer_radar.operator.exchange_dry_run import (
    build_current_exchange_dry_run,
    build_exchange_dry_run,
)
from src.app.hammer_radar.operator.eth_paper_candidates import (
    build_eth_candidates_payload,
    build_eth_paper_candidate,
    build_eth_paper_summary,
)
from src.app.hammer_radar.operator.eth_paper_outcomes import (
    build_eth_paper_outcome,
    build_eth_paper_outcome_summary,
    build_eth_paper_outcomes_payload,
)
from src.app.hammer_radar.operator.first_live_runbook import (
    build_first_live_runbook,
    evaluate_first_live_runbook,
    first_live_runbook_evaluations_path,
    load_first_live_runbook_evaluations,
)
from src.app.hammer_radar.operator.first_live_operator_approval_cockpit import (
    build_operator_approval_cockpit_state,
    operator_approval_cockpit_html,
    record_operator_approval_cockpit_intent,
)
from src.app.hammer_radar.operator.lane_control_cockpit import (
    build_lane_control_cockpit_state,
    render_lane_control_cockpit_html,
)
from src.app.hammer_radar.operator.tiny_live_controls_arming import (
    build_tiny_live_controls_review,
)
from src.app.hammer_radar.operator.tiny_live_final_console import (
    build_tiny_live_final_console,
    render_tiny_live_final_console_html,
)
from src.app.hammer_radar.operator.tiny_live_actual_submit_reconciliation import (
    build_tiny_live_actual_submit_reconciliation,
)
from src.app.hammer_radar.operator.tiny_live_jit_launch_packet import (
    build_tiny_live_jit_launch_packet,
)
from src.app.hammer_radar.operator.tiny_live_binance_autonomous_readiness_binding import (
    build_tiny_live_binance_autonomous_readiness_binding,
)
from src.app.hammer_radar.operator.tiny_live_risk_contract_fix import (
    build_tiny_live_risk_contract_diagnostic,
)
from src.app.hammer_radar.operator.live_safety import (
    build_current_live_safety,
    evaluate_live_safety,
)
from src.app.hammer_radar.operator.live_approval import (
    evaluate_live_approval_request,
    live_approval_requests_path,
    load_live_approval_requests,
)
from src.app.hammer_radar.operator.live_begins import (
    build_live_begins_status,
    evaluate_and_record_live_begins,
    live_begins_events_path,
    load_live_begins_events,
)
from src.app.hammer_radar.operator.live_execution_preview import (
    build_live_execution_preview,
    evaluate_and_record_live_execution_preview,
    live_execution_previews_path,
    load_live_execution_previews,
)
from src.app.hammer_radar.operator.live_execution_intent import (
    create_live_execution_intent,
    list_live_execution_intents,
)
from src.app.hammer_radar.operator.live_executor_rehearsal import (
    create_live_executor_rehearsal,
    list_live_executor_rehearsals,
)
from src.app.hammer_radar.operator.live_arming_checklist import (
    build_live_arming_status,
    evaluate_and_record_live_arming_check,
    list_live_arming_checks,
)
from src.app.hammer_radar.operator.first_live_execution_gate import (
    build_first_live_execution_gate,
    evaluate_and_record_first_live_execution_gate,
    list_first_live_execution_gates,
)
from src.app.hammer_radar.operator.first_live_adapter_verification import (
    build_first_live_adapter_status,
    evaluate_and_record_first_live_adapter_check,
    list_first_live_adapter_checks,
)
from src.app.hammer_radar.operator.first_live_readiness import (
    build_first_live_readiness_status,
    evaluate_and_record_first_live_readiness,
    list_first_live_readiness_checks,
)
from src.app.hammer_radar.operator.first_live_ladder_submit_adapter import (
    build_first_live_ladder_submit_status,
    evaluate_and_record_first_live_ladder_submit_check,
    list_first_live_ladder_submit_checks,
)
from src.app.hammer_radar.operator.first_live_protective_adapter import (
    build_first_live_protective_status,
    evaluate_and_record_first_live_protective_check,
    list_first_live_protective_checks,
)
from src.app.hammer_radar.operator.first_live_test_order_gate import (
    build_first_live_test_order_status,
    evaluate_and_record_first_live_test_order_check,
    list_first_live_test_order_checks,
)
from src.app.hammer_radar.operator.first_live_chain_runbook import (
    build_first_live_chain_status,
    evaluate_and_record_first_live_chain_check,
    list_first_live_chain_checks,
)
from src.app.hammer_radar.operator.first_live_candidate_queue import (
    build_first_live_candidate_queue,
    clear_selected_signal,
    select_first_live_candidate,
)
from src.app.hammer_radar.operator.first_live_higher_timeframe_policy import get_higher_timeframe_live_policy
from src.app.hammer_radar.operator.first_live_timeframe_policy import get_first_live_timeframe_policy
from src.app.hammer_radar.operator.first_microscopic_live_attempt import (
    build_first_microscopic_live_profile,
    build_first_microscopic_live_status,
    check_first_microscopic_live_attempt,
    execute_first_microscopic_live_attempt,
    list_first_microscopic_live_attempts,
)
from src.app.hammer_radar.operator.live_executor_transport import (
    attempt_live_executor_transport,
    build_live_executor_transport_status,
    check_live_executor_transport,
    list_live_executor_transport_attempts,
)
from src.app.hammer_radar.operator.live_arming_runbook import (
    build_live_arming_runbook,
    evaluate_and_record_live_arming_runbook,
    list_live_arming_runbooks,
)
from src.app.hammer_radar.operator.live_policy_arming import (
    build_live_policy_arming_runbook,
    build_live_policy_arming_status,
    evaluate_and_record_live_policy_arming_check,
)
from src.app.hammer_radar.operator.live_policy_dry_chain_smoke import (
    build_policy_armed_dry_chain_runbook,
    build_policy_armed_dry_chain_smoke_status,
    run_policy_armed_dry_chain_smoke,
)
from src.app.hammer_radar.operator.funded_tiny_live_readiness import (
    build_funded_tiny_live_readiness_check,
    build_funded_tiny_live_readiness_runbook,
    build_funded_tiny_live_readiness_status,
)
from src.app.hammer_radar.operator.post_funding_balance_verification import (
    build_post_funding_balance_runbook,
    build_post_funding_balance_status,
    evaluate_and_record_post_funding_balance_check,
)
from src.app.hammer_radar.operator.rehearsal_test_order_protective_readiness import (
    build_rehearsal_test_order_protective_check,
    build_rehearsal_test_order_protective_runbook,
    build_rehearsal_test_order_protective_status,
)
from src.app.hammer_radar.operator.final_protected_live_gate_review import (
    build_final_protected_live_gate_check,
    build_final_protected_live_gate_runbook,
    build_final_protected_live_gate_status,
)
from src.app.hammer_radar.operator.live_preflight import (
    build_promoted_strategy_preflight,
    evaluate_and_record_live_preflight,
    live_preflight_packs_path,
    load_live_preflight_packs,
)
from src.app.hammer_radar.operator.live_connector_stub import (
    CONNECTOR_MODE,
    load_live_attempts,
    submit_live_order_stub,
)
from src.app.hammer_radar.operator.inspect import (
    LIVE_DECISION_ELIGIBLE,
    LIVE_DECISION_FORBIDDEN,
    LiveCandidateCheck,
    build_live_candidate_snapshot,
)
from src.app.hammer_radar.operator.manual_outcomes import (
    append_manual_outcome,
    load_manual_outcomes,
)
from src.app.hammer_radar.operator.notification_watcher import (
    check_notifications,
    load_alert_records,
    notification_status,
)
from src.app.hammer_radar.operator.operator_actions import (
    append_operator_action,
    build_operator_action_record,
    load_operator_actions,
    operator_actions_path,
    parse_operator_action,
)
from src.app.hammer_radar.operator.market_intelligence import (
    build_market_intelligence_summary,
    build_market_rankings,
    build_market_snapshots_payload,
    evaluate_ethbtc_rotation,
)
from src.app.hammer_radar.operator.markov_regime_gate import build_markov_regime_gate
from src.app.hammer_radar.operator.miro_fish_quality_gate import build_miro_fish_quality_gate
from src.app.hammer_radar.operator.final_human_review_packet import (
    build_final_human_review_packet,
    build_final_human_review_packets_payload,
)
from src.app.hammer_radar.operator.human_confirmation_records import (
    build_human_confirmation_records,
    build_human_confirmation_records_status,
)
from src.app.hammer_radar.operator.review_record_aggregator import build_review_record_arming_snapshot
from src.app.hammer_radar.operator.source_warning_review import build_source_warning_review
from src.app.hammer_radar.operator.source_chain_repair import build_source_chain_repair
from src.app.hammer_radar.operator.candidate_revalidation_watch import build_candidate_revalidation_watch
from src.app.hammer_radar.operator.dual_lane_candidate_watch import build_dual_lane_candidate_watch
from src.app.hammer_radar.operator.betrayal_true_paper_tracking import build_betrayal_true_paper_scaffold
from src.app.hammer_radar.operator.betrayal_paper_outcome_ledger import (
    build_betrayal_paper_outcome_status,
    record_betrayal_paper_outcome,
)
from src.app.hammer_radar.operator.betrayal_paper_signal_detector import (
    build_betrayal_paper_signal_detector_status,
    run_betrayal_paper_signal_detector,
)
from src.app.hammer_radar.operator.betrayal_detector_source_wiring import (
    build_betrayal_detector_source_wiring,
)
from src.app.hammer_radar.operator.betrayal_source_signal_emitter import (
    build_betrayal_source_signal_emitter_status,
    load_emitted_betrayal_paper_signals,
    run_betrayal_source_signal_emitter,
)
from src.app.hammer_radar.operator.live_arming_preflight import build_live_arming_preflight
from src.app.hammer_radar.operator.live_env_arming_checklist import (
    build_live_env_arming_checklist,
    build_live_env_arming_checklist_status,
)
from src.app.hammer_radar.operator.live_env_boundary_review import build_live_env_boundary_review
from src.app.hammer_radar.operator.tiny_live_risk_contract import build_tiny_live_risk_contract_payload
from src.app.hammer_radar.operator.tiny_live_ticket_builder import (
    build_tiny_live_ticket,
    build_tiny_live_tickets_payload,
)
from src.app.hammer_radar.operator.multi_symbol_scanner import (
    build_multi_symbol_scans_payload,
    build_multi_symbol_summary,
    scan_watchlist,
)
from src.app.hammer_radar.operator.paper_execution import (
    execute_paper_ticket,
    load_paper_executions,
)
from src.app.hammer_radar.operator.paper_refresh_scheduler import (
    build_refresh_runs_payload,
    run_refresh_sequence,
    scheduler_status,
)
from src.app.hammer_radar.operator.readiness import build_readiness_payload
from src.app.hammer_radar.operator.strategy_performance import (
    build_live_eligibility_matrix,
    build_strategy_entry_mode_summary,
    build_strategy_performance_summary,
    build_strategy_timeframe_summary,
)
from src.app.hammer_radar.operator.strategy_promotion_watcher import (
    build_live_qualified_fresh_candidate_watch,
    build_strategy_promotion_status,
    check_strategy_promotions,
    load_strategy_promotion_events,
    strategy_promotion_events_path,
)
from src.app.hammer_radar.operator.tiny_live_autonomous_armed_dry_run import (
    arm_autonomous_dry_run_lane,
    build_autonomous_dry_run_arming_status,
    build_tiny_live_autonomous_armed_dry_run,
    disarm_autonomous_dry_run_lane,
)
from src.app.hammer_radar.operator.telegram_approval_challenge import (
    create_first_live_approval_challenge,
    load_telegram_approval_challenges,
    process_first_live_challenge_reply,
    telegram_approval_challenges_path,
)
from src.app.hammer_radar.operator.telegram_operator_bridge import (
    handle_telegram_operator_command,
    load_telegram_operator_commands,
    telegram_operator_commands_path,
)
from src.app.hammer_radar.operator.telegram_polling_worker import (
    poll_telegram_once,
    polling_state,
    polling_status,
)
from src.app.hammer_radar.operator.trade_ticket import (
    approve_paper_ticket,
    build_trade_ticket,
    load_trade_ticket_records,
)

SERVICE_NAME = "hammer_radar_approval_api"
DECISIONS_FILENAME = "manual_decisions.ndjson"
LIVE_EXECUTION_ENABLED = False
ORDER_PLACED = False
DEFAULT_MAX_POSITION_USD = 44.0
DEFAULT_MAX_LEVERAGE = 3.0

DecisionValue = Literal["approve_manual_live", "reject", "paper_only", "watch"]
ManualOutcomeResult = Literal["win", "loss", "breakeven", "skipped"]

app = FastAPI(title="Hammer Radar Approval API")


class DecisionRequest(BaseModel):
    signal_id: str = Field(min_length=1)
    decision: DecisionValue
    operator: str = Field(min_length=1)
    notes: str = ""
    intended_position_usd: float | None = None
    intended_leverage: float | None = None
    override_reason: str | None = None


class ManualOutcomeRequest(BaseModel):
    signal_id: str = Field(min_length=1)
    result: ManualOutcomeResult
    entry_price: float | None = None
    exit_price: float | None = None
    position_usd: float | None = None
    leverage: float | None = None
    pnl_usd: float | None = None
    pnl_pct: float | None = None
    notes: str = ""


class ApprovePaperTicketRequest(BaseModel):
    ticket_id: str = Field(min_length=1)
    operator: str = Field(min_length=1)
    notes: str = ""
    ticket_snapshot: dict | None = None


class ExecutePaperTicketRequest(BaseModel):
    ticket_id: str = Field(min_length=1)
    operator: str = Field(min_length=1)
    notes: str = ""


class ExchangeDryRunRequest(BaseModel):
    ticket: dict


class LiveSafetyEvaluateRequest(BaseModel):
    readiness: dict | None = None
    ticket: dict | None = None
    exchange_dry_run: dict | None = None
    decisions: list[dict] | None = None
    paper_executions: list[dict] | None = None
    manual_outcomes: list[dict] | None = None
    config_override: dict | None = None


class LiveConnectorSubmitRequest(BaseModel):
    ticket_id: str = Field(min_length=1)
    operator: str = Field(min_length=1)
    notes: str = ""


class TinyLiveTicketBuildRequest(BaseModel):
    dry_run: bool = True
    write: bool = False
    candidate_id: str | None = None
    approval_phrase: str | None = None
    operator_note: str | None = None


class TinyLiveAutonomousDryRunArmLaneRequest(BaseModel):
    lane_key: str = Field(min_length=1)
    operator_id: str = Field(default="local_operator", min_length=1)
    reason: str = ""
    confirm_dry_run_autonomous_arming: str | None = None


class TinyLiveAutonomousDryRunDisarmRequest(BaseModel):
    lane_key: str | None = "all"
    operator_id: str = Field(default="local_operator", min_length=1)
    reason: str = ""
    confirm_dry_run_autonomous_disarm: str | None = None


class LiveEnvChecklistConfirmRequest(BaseModel):
    dry_run: bool = True
    write: bool = False
    candidate_id: str | None = None
    risk_contract_hash: str | None = None
    manual_funding_phrase: str | None = None
    live_env_review_phrase: str | None = None
    max_loss_ack_phrase: str | None = None
    exact_candidate_ack_phrase: str | None = None
    operator_note: str | None = None


class LiveEnvBoundaryReviewReportRequest(BaseModel):
    dry_run: bool = True
    write: bool = False
    candidate_id: str | None = None


class FinalHumanReviewPacketBuildRequest(BaseModel):
    dry_run: bool = True
    write: bool = False
    candidate_id: str | None = None
    final_approval_phrase: str | None = None
    operator_note: str | None = None


class HumanConfirmationRecordRequest(BaseModel):
    dry_run: bool = True
    write: bool = False
    candidate_id: str | None = None
    r85_approval_phrase: str | None = None
    r86_manual_funding_phrase: str | None = None
    r86_live_env_review_phrase: str | None = None
    r86_max_loss_ack_phrase: str | None = None
    r86_exact_candidate_ack_phrase: str | None = None
    r88_final_approval_phrase: str | None = None
    operator_note: str | None = None


class ReadinessSnapshotReportRequest(BaseModel):
    dry_run: bool = True
    write: bool = False
    candidate_id: str | None = None


class SourceWarningReviewReportRequest(BaseModel):
    dry_run: bool = True
    write: bool = False
    candidate_id: str | None = None


class SourceChainRepairReportRequest(BaseModel):
    dry_run: bool = True
    write: bool = False
    candidate_id: str | None = None


class CandidateRevalidationWatchReportRequest(BaseModel):
    dry_run: bool = True
    write: bool = False
    candidate_id: str | None = None


class DualLaneCandidateWatchReportRequest(BaseModel):
    dry_run: bool = True
    write: bool = False
    candidate_id: str | None = None


class BetrayalTruePaperScaffoldReportRequest(BaseModel):
    dry_run: bool = True
    write: bool = False
    symbol: str | None = None
    max_candidates: int | None = None


class BetrayalPaperOutcomeRecordRequest(BaseModel):
    dry_run: bool = True
    write: bool = False
    outcome: dict[str, Any] | None = None


class BetrayalPaperSignalDetectorRunRequest(BaseModel):
    dry_run: bool = True
    write: bool = False
    max_signals: int | None = None
    identity_filter: str | None = None
    allow_open_tracking: bool = True
    allow_closed_outcomes: bool = True


class BetrayalDetectorSourceWiringReportRequest(BaseModel):
    dry_run: bool = True
    write: bool = False
    symbol: str | None = None
    timeframe: str | None = None


class BetrayalSourceSignalEmitterRunRequest(BaseModel):
    dry_run: bool = True
    write: bool = False
    max_signals: int | None = None
    identity_filter: str | None = None
    allow_historical_replay: bool = True
    allow_fresh_current: bool = False


class LiveExecutionIntentRequest(BaseModel):
    signal_id: str | None = None
    approval_code: str | None = None
    dry_run: bool = True


class LivePolicyDryChainRequest(BaseModel):
    scenario: str = "micro"
    signal_id: str | None = None


class PostFundingBalanceRequest(BaseModel):
    available_usdt: float | None = None


class RehearsalTestOrderProtectiveReadinessRequest(BaseModel):
    signal_id: str | None = None
    execution_intent_id: str | None = None
    available_usdt: float | None = None


class FinalProtectedLiveGateRequest(BaseModel):
    available_usdt: float | None = None
    signal_id: str | None = None
    execution_intent_id: str | None = None


class LiveExecutorRehearsalRequest(BaseModel):
    execution_intent_id: str | None = None
    signal_id: str | None = None
    dry_run: bool = True


class FirstLiveExecutionGateRequest(BaseModel):
    execution_intent_id: str | None = None
    executor_rehearsal_id: str | None = None
    signal_id: str | None = None
    final_confirmation: bool = False
    dry_run: bool = True


class LiveExecutorTransportRequest(BaseModel):
    executor_rehearsal_id: str | None = None
    execution_intent_id: str | None = None
    signal_id: str | None = None
    transport_mode: str | None = None
    final_confirmation: bool = False
    dry_run: bool = True


class FirstMicroscopicLiveAttemptRequest(BaseModel):
    executor_rehearsal_id: str | None = None
    execution_intent_id: str | None = None
    signal_id: str | None = None
    final_confirmation: bool = False
    transport_mode: str | None = None
    dry_run: bool = True
    profile: dict | None = None


class FirstLiveLadderSubmitRequest(BaseModel):
    executor_rehearsal_id: str | None = None
    execution_intent_id: str | None = None
    signal_id: str | None = None
    transport_mode: str | None = None
    final_confirmation: bool = False
    dry_run: bool = True
    profile: dict | None = None


class FirstLiveProtectiveRequest(BaseModel):
    executor_rehearsal_id: str | None = None
    execution_intent_id: str | None = None
    signal_id: str | None = None
    transport_mode: str | None = None
    final_confirmation: bool = False
    dry_run: bool = True


class FirstLiveTestOrderRequest(BaseModel):
    signal_id: str | None = None
    execution_intent_id: str | None = None
    executor_rehearsal_id: str | None = None
    transport_mode: str | None = None
    dry_run: bool = True
    final_confirmation: bool = False


class FirstLiveCandidateSelectRequest(BaseModel):
    signal_id: str = Field(min_length=1)
    source: str = "api"
    reason: str = ""


class FirstLiveCandidateClearRequest(BaseModel):
    source: str = "api"
    reason: str = ""


class BetrayalShadowTrackRequest(BaseModel):
    latest_only: bool = True
    limit: int = 20
    since_hours: int = 24
    symbol: str | None = None
    min_betrayal_score: int = 50


class BetrayalShadowResolveRequest(BaseModel):
    limit: int = 0
    symbol: str | None = None
    timeframe: str | None = None
    dry_run: bool = True
    write: bool = False
    since_hours: int | None = None


class BetrayalCandleArchiveRequest(BaseModel):
    dry_run: bool = True
    write: bool = False
    symbol: str | None = None
    timeframe: str | None = None
    limit: int = 0
    since_hours: int | None = None


class BetrayalCandleCaptureRequest(BaseModel):
    dry_run: bool = True
    write: bool = False
    symbol: str | None = None
    timeframe: str | None = None
    limit: int = 0
    since_hours: int | None = None
    source_mode: str = SOURCE_MODE_LOCAL_ONLY


class NotificationCheckRequest(BaseModel):
    send: bool = False
    channel: Literal["telegram", "none"] = "none"


class PaperRefreshRunRequest(BaseModel):
    tasks: list[str] | None = None
    use_network: bool = False
    write_outputs: bool = True
    send_notifications: bool = False


class OperatorActionRequest(BaseModel):
    text: str = Field(min_length=1)
    source: str = "approval_api"
    signal_id: str | None = None
    alert_id: str | None = None


class OperatorParseActionRequest(BaseModel):
    text: str = Field(min_length=1)
    signal_id: str | None = None


class LiveApprovalEvaluateRequest(BaseModel):
    text: str = Field(min_length=1)
    source: str = "approval_api"


class TelegramOperatorCommandRequest(BaseModel):
    text: str = Field(min_length=1)
    source: str = "manual"
    chat_id: str | None = None
    update_id: int | None = None


class TelegramChallengeReplyRequest(BaseModel):
    text: str = Field(min_length=1)
    source: str = "manual"


class TelegramPollingOnceRequest(BaseModel):
    dry_run: bool = False
    send_responses: bool = True
    max_updates: int = Field(default=10, ge=1, le=100)


class StrategyPromotionCheckRequest(BaseModel):
    record_blocked: bool = False


class BinanceLiveTestOrderRequest(BaseModel):
    use_mock_adapter: bool = False
    require_exact_approval: bool | None = None


class BinanceLiveExecuteRequest(BaseModel):
    signal_id: str | None = None
    use_mock_adapter: bool = False
    require_test_order_first: bool = True
    require_protective_orders: bool = True


class BinanceProtectiveRequest(BaseModel):
    use_mock_adapter: bool = False


class TinyLiveControlsReviewRecordRequest(BaseModel):
    confirm_tiny_live_controls_review: str = Field(min_length=1)
    operator_id: str = "local_operator"
    reason: str | None = None


class TinyLiveControlsArmRequest(BaseModel):
    confirm_arm_tiny_live_controls: str = Field(min_length=1)
    operator_id: str = "local_operator"
    reason: str | None = None


class TinyLiveFinalConsoleReviewRecordRequest(BaseModel):
    confirm_final_console_review: str = Field(min_length=1)
    operator_id: str = "local_operator"
    reason: str | None = None


class TinyLiveFinalConsoleControlsArmRequest(BaseModel):
    confirm_final_console_controls_arming: str = Field(min_length=1)
    operator_id: str = "local_operator"
    reason: str | None = None


class TinyLiveActualSubmitDryPreviewRequest(BaseModel):
    confirm_actual_submit_dry_preview: str = Field(min_length=1)
    operator_id: str = "local_operator"
    reason: str | None = None


class TinyLiveActualSubmitExecuteRequest(BaseModel):
    confirm_actual_live_submit: str = Field(min_length=1)
    allow_binance_order_endpoint: bool = False
    operator_id: str = "local_operator"
    reason: str | None = None


class TinyLiveJitLaunchPacketRunRequest(BaseModel):
    confirm_jit_launch_prep: str = Field(min_length=1)
    record_jit_launch_packet: bool = True
    confirm_final_manual_submit_unlock: str | None = None
    operator_id: str = "local_operator"
    reason: str | None = None


class TinyLiveRiskContractDiagnosticRecordRequest(BaseModel):
    confirm_risk_contract_diagnostic: str = Field(min_length=1)
    operator_id: str = "local_operator"
    reason: str | None = None


class TinyLiveRiskContractFixApplyRequest(BaseModel):
    confirm_risk_contract_fix: str = Field(min_length=1)
    operator_id: str = "local_operator"
    reason: str | None = None


class OperatorApprovalCockpitIntentRequest(BaseModel):
    candidate_id: str = Field(min_length=1)
    intent: Literal["APPROVE", "REJECT", "WAIT"]
    counsel_decision: Literal["APPROVE", "REJECT", "WAIT", "ESCALATE"]
    counsel_tags: list[str] = Field(default_factory=list, max_length=12)
    risk_contract_hash: str = Field(min_length=1)
    packet_hash: str = Field(min_length=1)
    operator_note: str | None = None


WatchlistCategory = Literal["CORE_LIVE", "CORE_WATCH", "RELATIVE_STRENGTH", "LIQUID_MAJOR", "HIGH_BETA"]


@app.get("/", response_class=HTMLResponse)
@app.get("/ui", response_class=HTMLResponse)
def operator_ui() -> str:
    return _operator_ui_html()


@app.get("/operator/approval-cockpit", response_class=HTMLResponse)
def operator_approval_cockpit() -> str:
    return operator_approval_cockpit_html()


@app.get("/operator/approval-cockpit/state")
def operator_approval_cockpit_state(
    candidate_id: str = "normal|BTCUSDT|13m|long|ladder_close_50_618",
) -> dict:
    return build_operator_approval_cockpit_state(candidate_id=candidate_id, log_dir=get_log_dir(use_env=True))


@app.get("/operator/lane-cockpit", response_class=HTMLResponse)
def operator_lane_cockpit() -> str:
    return render_lane_control_cockpit_html()


@app.get("/operator/lane-cockpit/state")
def operator_lane_cockpit_state(
    lane_key: str = "BTCUSDT|13m|long|ladder_close_50_618",
) -> dict:
    return build_lane_control_cockpit_state(lane_key=lane_key, log_dir=get_log_dir(use_env=True))


@app.get("/tiny-live/controls/review")
def tiny_live_controls_review() -> dict:
    return build_tiny_live_controls_review(log_dir=get_log_dir(use_env=True))


@app.post("/tiny-live/controls/review/record")
def tiny_live_controls_review_record(request: TinyLiveControlsReviewRecordRequest) -> dict:
    return build_tiny_live_controls_review(
        log_dir=get_log_dir(use_env=True),
        record_controls_review=True,
        confirm_tiny_live_controls_review=request.confirm_tiny_live_controls_review,
        operator_id=request.operator_id,
        reason=request.reason,
    )


@app.post("/tiny-live/controls/arm")
def tiny_live_controls_arm(request: TinyLiveControlsArmRequest) -> dict:
    return build_tiny_live_controls_review(
        log_dir=get_log_dir(use_env=True),
        arm_tiny_live_controls=True,
        confirm_arm_tiny_live_controls=request.confirm_arm_tiny_live_controls,
        operator_id=request.operator_id,
        reason=request.reason,
    )


@app.get("/tiny-live/final-console")
def tiny_live_final_console() -> dict:
    return build_tiny_live_final_console(log_dir=get_log_dir(use_env=True))


@app.get("/operator/tiny-live/final-console", response_class=HTMLResponse)
def operator_tiny_live_final_console() -> str:
    return render_tiny_live_final_console_html()


@app.post("/tiny-live/final-console/review/record")
def tiny_live_final_console_review_record(request: TinyLiveFinalConsoleReviewRecordRequest) -> dict:
    return build_tiny_live_final_console(
        log_dir=get_log_dir(use_env=True),
        record_final_console_review=True,
        confirm_final_console_review=request.confirm_final_console_review,
        operator_id=request.operator_id,
        reason=request.reason,
    )


@app.post("/tiny-live/final-console/controls/arm")
def tiny_live_final_console_controls_arm(request: TinyLiveFinalConsoleControlsArmRequest) -> dict:
    return build_tiny_live_final_console(
        log_dir=get_log_dir(use_env=True),
        arm_controls_from_final_console=True,
        confirm_final_console_controls_arming=request.confirm_final_console_controls_arming,
        operator_id=request.operator_id,
        reason=request.reason,
    )


@app.get("/tiny-live/actual-submit/reconcile")
def tiny_live_actual_submit_reconcile() -> dict:
    return build_tiny_live_actual_submit_reconciliation(log_dir=get_log_dir(use_env=True))


@app.post("/tiny-live/actual-submit/dry-preview")
def tiny_live_actual_submit_dry_preview(request: TinyLiveActualSubmitDryPreviewRequest) -> dict:
    return build_tiny_live_actual_submit_reconciliation(
        log_dir=get_log_dir(use_env=True),
        dry_run_actual_submit_reconcile=True,
        record_actual_submit_preview=True,
        confirm_actual_submit_dry_preview=request.confirm_actual_submit_dry_preview,
        operator_id=request.operator_id,
        reason=request.reason,
    )


@app.post("/tiny-live/actual-submit/execute")
def tiny_live_actual_submit_execute(request: TinyLiveActualSubmitExecuteRequest) -> dict:
    return build_tiny_live_actual_submit_reconciliation(
        log_dir=get_log_dir(use_env=True),
        execute_actual_live_submit=True,
        allow_binance_order_endpoint=request.allow_binance_order_endpoint,
        confirm_actual_live_submit=request.confirm_actual_live_submit,
        operator_id=request.operator_id,
        reason=request.reason,
    )


@app.get("/tiny-live/jit-launch-packet")
def tiny_live_jit_launch_packet() -> dict:
    return build_tiny_live_jit_launch_packet(log_dir=get_log_dir(use_env=True))


@app.get("/tiny-live/qualified-candidate-watch")
def tiny_live_qualified_candidate_watch() -> dict:
    return build_live_qualified_fresh_candidate_watch(log_dir=get_log_dir(use_env=True))


@app.get("/tiny-live/autonomous-armed-dry-run")
def tiny_live_autonomous_armed_dry_run() -> dict:
    return build_tiny_live_autonomous_armed_dry_run(log_dir=get_log_dir(use_env=True))


@app.get("/tiny-live/autonomous-arming/status")
def tiny_live_autonomous_arming_status() -> dict:
    return build_autonomous_dry_run_arming_status(log_dir=get_log_dir(use_env=True))


@app.get("/tiny-live/binance-autonomous-readiness")
def tiny_live_binance_autonomous_readiness(
    fetch_readonly_precision: bool = Query(False),
    confirm: str | None = Query(None),
) -> dict:
    return build_tiny_live_binance_autonomous_readiness_binding(
        log_dir=get_log_dir(use_env=True),
        fetch_binance_readonly_precision_mark_price=fetch_readonly_precision,
        confirm_tiny_live_binance_readonly_fetch=confirm,
    )


@app.get("/tiny-live/binance-account-read-env-discovery")
def tiny_live_binance_account_read_env_discovery() -> dict:
    return build_binance_account_read_env_discovery()


@app.post("/tiny-live/autonomous-arming/arm-dry-run-lane")
def tiny_live_autonomous_arming_arm_dry_run_lane(request: TinyLiveAutonomousDryRunArmLaneRequest) -> dict:
    return arm_autonomous_dry_run_lane(
        request.lane_key,
        request.operator_id,
        request.reason,
        log_dir=get_log_dir(use_env=True),
        confirm_dry_run_autonomous_arming=request.confirm_dry_run_autonomous_arming,
    )


@app.post("/tiny-live/autonomous-arming/disarm")
def tiny_live_autonomous_arming_disarm(request: TinyLiveAutonomousDryRunDisarmRequest) -> dict:
    return disarm_autonomous_dry_run_lane(
        request.lane_key,
        request.operator_id,
        request.reason,
        confirm_dry_run_autonomous_disarm=request.confirm_dry_run_autonomous_disarm,
    )


@app.post("/tiny-live/jit-launch-packet/run")
def tiny_live_jit_launch_packet_run(request: TinyLiveJitLaunchPacketRunRequest) -> dict:
    return build_tiny_live_jit_launch_packet(
        log_dir=get_log_dir(use_env=True),
        run_jit_launch_prep=True,
        record_jit_launch_packet=request.record_jit_launch_packet,
        confirm_jit_launch_prep=request.confirm_jit_launch_prep,
        confirm_final_manual_submit_unlock=request.confirm_final_manual_submit_unlock,
        operator_id=request.operator_id,
        reason=request.reason,
    )


@app.get("/tiny-live/risk-contract/review")
def tiny_live_risk_contract_review() -> dict:
    return build_tiny_live_risk_contract_diagnostic(log_dir=get_log_dir(use_env=True))


@app.post("/tiny-live/risk-contract/fix/record")
def tiny_live_risk_contract_fix_record(request: TinyLiveRiskContractDiagnosticRecordRequest) -> dict:
    return build_tiny_live_risk_contract_diagnostic(
        log_dir=get_log_dir(use_env=True),
        record_risk_contract_diagnostic=True,
        confirm_risk_contract_diagnostic=request.confirm_risk_contract_diagnostic,
        operator_id=request.operator_id,
        reason=request.reason,
    )


@app.post("/tiny-live/risk-contract/fix/apply")
def tiny_live_risk_contract_fix_apply(request: TinyLiveRiskContractFixApplyRequest) -> dict:
    return build_tiny_live_risk_contract_diagnostic(
        log_dir=get_log_dir(use_env=True),
        apply_risk_contract_fix=True,
        confirm_risk_contract_fix=request.confirm_risk_contract_fix,
        operator_id=request.operator_id,
        reason=request.reason,
    )


@app.post("/operator/approval-cockpit/intent")
def operator_approval_cockpit_intent(request: OperatorApprovalCockpitIntentRequest) -> dict:
    result = record_operator_approval_cockpit_intent(
        candidate_id=request.candidate_id,
        intent=request.intent,
        counsel_decision=request.counsel_decision,
        counsel_tags=request.counsel_tags,
        risk_contract_hash=request.risk_contract_hash,
        packet_hash=request.packet_hash,
        operator_note=request.operator_note,
        log_dir=get_log_dir(use_env=True),
    )
    if not result.get("accepted_as_intent"):
        raise HTTPException(status_code=400, detail=result)
    return result


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "service": SERVICE_NAME,
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
    }


@app.get("/readiness")
def readiness() -> dict:
    return build_readiness_payload(log_dir=get_log_dir(use_env=True))


@app.get("/trade-ticket")
def trade_ticket(
    signal_id: str | None = None,
    latest_only: bool = True,
    allow_short: bool = False,
    max_position_usd: float | None = Query(default=None, gt=0),
    max_risk_usd: float = Query(default=5.0, gt=0),
    max_leverage: float | None = Query(default=None, gt=0),
    fresh_minutes: int = Query(default=30, ge=0),
) -> dict:
    return build_trade_ticket(
        signal_id=signal_id,
        latest_only=latest_only,
        allow_short=allow_short,
        max_position_usd=max_position_usd,
        max_risk_usd=max_risk_usd,
        max_leverage=max_leverage,
        fresh_minutes=fresh_minutes,
        log_dir=get_log_dir(use_env=True),
    )


@app.post("/trade-ticket/approve-paper")
def approve_paper_trade_ticket(request: ApprovePaperTicketRequest) -> dict:
    try:
        return approve_paper_ticket(
            ticket_id=request.ticket_id,
            operator=request.operator,
            notes=request.notes,
            ticket_snapshot=request.ticket_snapshot,
            log_dir=get_log_dir(use_env=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/trade-tickets")
def trade_tickets(limit: int = Query(default=50, ge=0), ticket_id: str | None = None) -> dict:
    records = load_trade_ticket_records(limit=limit, ticket_id=ticket_id, log_dir=get_log_dir(use_env=True))
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "paper_execution_enabled": False,
        "paper_order_placed": False,
        "trade_tickets": records,
    }


@app.post("/trade-ticket/execute-paper")
def execute_paper_trade_ticket(request: ExecutePaperTicketRequest) -> dict:
    try:
        return execute_paper_ticket(
            ticket_id=request.ticket_id,
            operator=request.operator,
            notes=request.notes,
            log_dir=get_log_dir(use_env=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/paper-executions")
def paper_executions(
    limit: int = Query(default=50, ge=0),
    signal_id: str | None = None,
    status: str | None = None,
) -> dict:
    records = load_paper_executions(
        limit=limit,
        signal_id=signal_id,
        status=status,
        log_dir=get_log_dir(use_env=True),
    )
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "paper_executions": records,
    }


@app.get("/exchange-dry-run")
def exchange_dry_run(
    signal_id: str | None = None,
    allow_short: bool = False,
    max_position_usd: float = Query(default=DEFAULT_MAX_POSITION_USD, gt=0),
    max_risk_usd: float = Query(default=5.0, gt=0),
    max_leverage: float = Query(default=DEFAULT_MAX_LEVERAGE, gt=0),
    fresh_minutes: int = Query(default=30, ge=0),
) -> dict:
    return build_current_exchange_dry_run(
        signal_id=signal_id,
        allow_short=allow_short,
        max_position_usd=max_position_usd,
        max_risk_usd=max_risk_usd,
        max_leverage=max_leverage,
        fresh_minutes=fresh_minutes,
        log_dir=get_log_dir(use_env=True),
    )


@app.post("/exchange-dry-run/from-ticket")
def exchange_dry_run_from_ticket(request: ExchangeDryRunRequest) -> dict:
    return build_exchange_dry_run(request.ticket)


@app.get("/live-safety")
def live_safety(
    signal_id: str | None = None,
    allow_short: bool = False,
    max_position_usd: float = Query(default=DEFAULT_MAX_POSITION_USD, gt=0),
    max_leverage: float = Query(default=DEFAULT_MAX_LEVERAGE, gt=0),
    fresh_minutes: int = Query(default=30, ge=0),
) -> dict:
    return build_current_live_safety(
        signal_id=signal_id,
        allow_short=allow_short,
        max_position_usd=max_position_usd,
        max_leverage=max_leverage,
        fresh_minutes=fresh_minutes,
        log_dir=get_log_dir(use_env=True),
    )


@app.post("/live-safety/evaluate")
def live_safety_evaluate(request: LiveSafetyEvaluateRequest) -> dict:
    return evaluate_live_safety(
        readiness=request.readiness,
        ticket=request.ticket,
        exchange_dry_run=request.exchange_dry_run,
        decisions=request.decisions,
        paper_executions=request.paper_executions,
        manual_outcomes=request.manual_outcomes,
        config_override=request.config_override,
    )


@app.get("/live/begins/status")
def live_begins_status() -> dict:
    return build_live_begins_status(log_dir=get_log_dir(use_env=True))


@app.post("/live/begins/check")
def live_begins_check() -> dict:
    return evaluate_and_record_live_begins(log_dir=get_log_dir(use_env=True))


@app.get("/live/begins/events")
def live_begins_events(limit: int = Query(default=50, ge=0), event_id: str | None = None) -> dict:
    log_dir = get_log_dir(use_env=True)
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "allow_live_orders": False,
        "global_kill_switch": True,
        "order_placed": ORDER_PLACED,
        "real_order_placed": False,
        "secrets_shown": False,
        "live_begins_events_path": str(live_begins_events_path(log_dir)),
        "live_begins_events": load_live_begins_events(limit=limit, event_id=event_id, log_dir=log_dir),
    }


@app.get("/live/execution/preview")
def live_execution_preview() -> dict:
    return build_live_execution_preview(log_dir=get_log_dir(use_env=True))


@app.post("/live/execution/preview")
def live_execution_preview_check() -> dict:
    return evaluate_and_record_live_execution_preview(log_dir=get_log_dir(use_env=True))


@app.get("/live/execution/previews")
def live_execution_previews(limit: int = Query(default=50, ge=0), event_id: str | None = None) -> dict:
    log_dir = get_log_dir(use_env=True)
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "allow_live_orders": False,
        "global_kill_switch": True,
        "order_placed": ORDER_PLACED,
        "real_order_placed": False,
        "secrets_shown": False,
        "live_execution_previews_path": str(live_execution_previews_path(log_dir)),
        "live_execution_previews": load_live_execution_previews(limit=limit, event_id=event_id, log_dir=log_dir),
    }


@app.get("/live/execution/intents")
def live_execution_intents(limit: int = Query(default=20, ge=0), signal_id: str | None = None) -> dict:
    return list_live_execution_intents(limit=limit, signal_id=signal_id, log_dir=get_log_dir(use_env=True))


@app.post("/live/execution/intent")
def live_execution_intent(request: LiveExecutionIntentRequest | None = None) -> dict:
    request = request or LiveExecutionIntentRequest()
    return create_live_execution_intent(
        signal_id=request.signal_id,
        approval_code=request.approval_code,
        dry_run=request.dry_run,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/live/executor/rehearsals")
def live_executor_rehearsals(
    limit: int = Query(default=20, ge=0),
    signal_id: str | None = None,
    execution_intent_id: str | None = None,
) -> dict:
    return list_live_executor_rehearsals(
        limit=limit,
        signal_id=signal_id,
        execution_intent_id=execution_intent_id,
        log_dir=get_log_dir(use_env=True),
    )


@app.post("/live/executor/rehearsal")
def live_executor_rehearsal(request: LiveExecutorRehearsalRequest | None = None) -> dict:
    request = request or LiveExecutorRehearsalRequest()
    return create_live_executor_rehearsal(
        execution_intent_id=request.execution_intent_id,
        signal_id=request.signal_id,
        dry_run=request.dry_run,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/live/arming/status")
def live_arming_status() -> dict:
    return build_live_arming_status(log_dir=get_log_dir(use_env=True))


@app.post("/live/arming/check")
def live_arming_check() -> dict:
    return evaluate_and_record_live_arming_check(log_dir=get_log_dir(use_env=True))


@app.get("/live/arming/checks")
def live_arming_checks(limit: int = Query(default=20, ge=0), status: str | None = None) -> dict:
    return list_live_arming_checks(limit=limit, status=status, log_dir=get_log_dir(use_env=True))


@app.get("/live/first-execution/gate")
def first_live_execution_gate_status() -> dict:
    return build_first_live_execution_gate(log_dir=get_log_dir(use_env=True))


@app.post("/live/first-execution/gate")
def first_live_execution_gate(request: FirstLiveExecutionGateRequest | None = None) -> dict:
    request = request or FirstLiveExecutionGateRequest()
    return evaluate_and_record_first_live_execution_gate(
        execution_intent_id=request.execution_intent_id,
        executor_rehearsal_id=request.executor_rehearsal_id,
        signal_id=request.signal_id,
        final_confirmation=request.final_confirmation,
        dry_run=request.dry_run,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/live/first-execution/gates")
def first_live_execution_gates(
    limit: int = Query(default=20, ge=0),
    signal_id: str | None = None,
    status: str | None = None,
) -> dict:
    return list_first_live_execution_gates(limit=limit, signal_id=signal_id, status=status, log_dir=get_log_dir(use_env=True))


@app.get("/live/executor/transport/status")
def live_executor_transport_status() -> dict:
    return build_live_executor_transport_status(log_dir=get_log_dir(use_env=True))


@app.post("/live/executor/transport/check")
def live_executor_transport_check(request: LiveExecutorTransportRequest | None = None) -> dict:
    request = request or LiveExecutorTransportRequest()
    return check_live_executor_transport(
        executor_rehearsal_id=request.executor_rehearsal_id,
        execution_intent_id=request.execution_intent_id,
        signal_id=request.signal_id,
        transport_mode=request.transport_mode,
        final_confirmation=request.final_confirmation,
        dry_run=request.dry_run,
        log_dir=get_log_dir(use_env=True),
    )


@app.post("/live/executor/transport/attempt")
def live_executor_transport_attempt(request: LiveExecutorTransportRequest | None = None) -> dict:
    request = request or LiveExecutorTransportRequest()
    return attempt_live_executor_transport(
        executor_rehearsal_id=request.executor_rehearsal_id,
        execution_intent_id=request.execution_intent_id,
        signal_id=request.signal_id,
        transport_mode=request.transport_mode,
        final_confirmation=request.final_confirmation,
        dry_run=request.dry_run,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/live/executor/transport/attempts")
def live_executor_transport_attempts(
    limit: int = Query(default=20, ge=0),
    signal_id: str | None = None,
    transport_mode: str | None = None,
    status: str | None = None,
) -> dict:
    return list_live_executor_transport_attempts(
        limit=limit,
        signal_id=signal_id,
        transport_mode=transport_mode,
        status=status,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/live/first-attempt/profile")
def first_microscopic_live_attempt_profile() -> dict:
    return build_first_microscopic_live_profile(log_dir=get_log_dir(use_env=True))


@app.get("/live/first-attempt/status")
def first_microscopic_live_attempt_status() -> dict:
    return build_first_microscopic_live_status(log_dir=get_log_dir(use_env=True))


@app.post("/live/first-attempt/check")
def first_microscopic_live_attempt_check(request: FirstMicroscopicLiveAttemptRequest | None = None) -> dict:
    request = request or FirstMicroscopicLiveAttemptRequest()
    return check_first_microscopic_live_attempt(
        executor_rehearsal_id=request.executor_rehearsal_id,
        execution_intent_id=request.execution_intent_id,
        signal_id=request.signal_id,
        transport_mode=request.transport_mode,
        final_confirmation=request.final_confirmation,
        dry_run=request.dry_run,
        profile=request.profile,
        log_dir=get_log_dir(use_env=True),
    )


@app.post("/live/first-attempt/execute")
def first_microscopic_live_attempt_execute(request: FirstMicroscopicLiveAttemptRequest | None = None) -> dict:
    request = request or FirstMicroscopicLiveAttemptRequest()
    return execute_first_microscopic_live_attempt(
        executor_rehearsal_id=request.executor_rehearsal_id,
        execution_intent_id=request.execution_intent_id,
        signal_id=request.signal_id,
        transport_mode=request.transport_mode,
        final_confirmation=request.final_confirmation,
        dry_run=request.dry_run,
        profile=request.profile,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/live/first-attempt/attempts")
def first_microscopic_live_attempts(
    limit: int = Query(default=20, ge=0),
    signal_id: str | None = None,
    transport_mode: str | None = None,
    status: str | None = None,
) -> dict:
    return list_first_microscopic_live_attempts(
        limit=limit,
        signal_id=signal_id,
        transport_mode=transport_mode,
        status=status,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/live/first-readiness/status")
def first_live_readiness_status() -> dict:
    return build_first_live_readiness_status(log_dir=get_log_dir(use_env=True))


@app.post("/live/first-readiness/check")
def first_live_readiness_check() -> dict:
    return evaluate_and_record_first_live_readiness(log_dir=get_log_dir(use_env=True))


@app.get("/live/first-readiness/checks")
def first_live_readiness_checks(limit: int = Query(default=20, ge=0), status: str | None = None) -> dict:
    return list_first_live_readiness_checks(limit=limit, status=status, log_dir=get_log_dir(use_env=True))


@app.get("/live/first-adapter/status")
def first_live_adapter_status() -> dict:
    return build_first_live_adapter_status(log_dir=get_log_dir(use_env=True))


@app.post("/live/first-adapter/check")
def first_live_adapter_check() -> dict:
    return evaluate_and_record_first_live_adapter_check(log_dir=get_log_dir(use_env=True))


@app.get("/live/first-adapter/checks")
def first_live_adapter_checks(limit: int = Query(default=20, ge=0), status: str | None = None) -> dict:
    return list_first_live_adapter_checks(limit=limit, status=status, log_dir=get_log_dir(use_env=True))


@app.get("/live/first-ladder/status")
def first_live_ladder_submit_status() -> dict:
    return build_first_live_ladder_submit_status(log_dir=get_log_dir(use_env=True))


@app.post("/live/first-ladder/check")
def first_live_ladder_submit_check(request: FirstLiveLadderSubmitRequest | None = None) -> dict:
    request = request or FirstLiveLadderSubmitRequest()
    return evaluate_and_record_first_live_ladder_submit_check(
        executor_rehearsal_id=request.executor_rehearsal_id,
        execution_intent_id=request.execution_intent_id,
        signal_id=request.signal_id,
        transport_mode=request.transport_mode,
        final_confirmation=request.final_confirmation,
        dry_run=request.dry_run,
        profile=request.profile,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/live/first-ladder/checks")
def first_live_ladder_submit_checks(limit: int = Query(default=20, ge=0), status: str | None = None) -> dict:
    return list_first_live_ladder_submit_checks(limit=limit, status=status, log_dir=get_log_dir(use_env=True))


@app.get("/live/first-protective/status")
def first_live_protective_status() -> dict:
    return build_first_live_protective_status(log_dir=get_log_dir(use_env=True))


@app.post("/live/first-protective/check")
def first_live_protective_check(request: FirstLiveProtectiveRequest | None = None) -> dict:
    request = request or FirstLiveProtectiveRequest()
    return evaluate_and_record_first_live_protective_check(
        executor_rehearsal_id=request.executor_rehearsal_id,
        execution_intent_id=request.execution_intent_id,
        signal_id=request.signal_id,
        transport_mode=request.transport_mode,
        final_confirmation=request.final_confirmation,
        dry_run=request.dry_run,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/live/first-protective/checks")
def first_live_protective_checks(limit: int = Query(default=20, ge=0), status: str | None = None) -> dict:
    return list_first_live_protective_checks(limit=limit, status=status, log_dir=get_log_dir(use_env=True))


@app.get("/live/first-test-order/status")
def first_live_test_order_status() -> dict:
    return build_first_live_test_order_status(log_dir=get_log_dir(use_env=True))


@app.post("/live/first-test-order/check")
def first_live_test_order_check(request: FirstLiveTestOrderRequest | None = None) -> dict:
    request = request or FirstLiveTestOrderRequest()
    return evaluate_and_record_first_live_test_order_check(
        signal_id=request.signal_id,
        execution_intent_id=request.execution_intent_id,
        executor_rehearsal_id=request.executor_rehearsal_id,
        transport_mode=request.transport_mode,
        dry_run=request.dry_run,
        final_confirmation=request.final_confirmation,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/live/first-test-order/checks")
def first_live_test_order_checks(limit: int = Query(default=20, ge=0), status: str | None = None) -> dict:
    return list_first_live_test_order_checks(limit=limit, status=status, log_dir=get_log_dir(use_env=True))


@app.get("/live/first-chain/status")
def first_live_chain_status(detail: str = Query(default="fast")) -> dict:
    return build_first_live_chain_status(log_dir=get_log_dir(use_env=True), detail=detail)


@app.post("/live/first-chain/check")
def first_live_chain_check(detail: str = Query(default="fast")) -> dict:
    return evaluate_and_record_first_live_chain_check(log_dir=get_log_dir(use_env=True), detail=detail)


@app.get("/live/first-chain/checks")
def first_live_chain_checks(limit: int = Query(default=20, ge=0), status: str | None = None) -> dict:
    return list_first_live_chain_checks(limit=limit, status=status, log_dir=get_log_dir(use_env=True))


@app.get("/live/first-candidates/status")
def first_live_candidates_status() -> dict:
    return build_first_live_candidate_queue(log_dir=get_log_dir(use_env=True))


@app.get("/live/higher-timeframe-policy/status")
def first_live_higher_timeframe_policy_status() -> dict:
    return get_higher_timeframe_live_policy()


@app.get("/live/timeframe-policy/status")
def first_live_timeframe_policy_status() -> dict:
    return get_first_live_timeframe_policy()


@app.get("/live/policy-arming/status")
def live_policy_arming_status() -> dict:
    return build_live_policy_arming_status()


@app.get("/live/policy-arming/runbook")
def live_policy_arming_runbook() -> dict:
    return build_live_policy_arming_runbook()


@app.post("/live/policy-arming/check")
def live_policy_arming_check() -> dict:
    return evaluate_and_record_live_policy_arming_check(log_dir=get_log_dir(use_env=True))


@app.get("/live/policy-dry-chain/status")
def live_policy_dry_chain_status() -> dict:
    return build_policy_armed_dry_chain_smoke_status(log_dir=get_log_dir(use_env=True))


@app.get("/live/policy-dry-chain/runbook")
def live_policy_dry_chain_runbook() -> dict:
    return build_policy_armed_dry_chain_runbook()


@app.post("/live/policy-dry-chain/check")
def live_policy_dry_chain_check(request: LivePolicyDryChainRequest | None = None) -> dict:
    request = request or LivePolicyDryChainRequest()
    return run_policy_armed_dry_chain_smoke(
        scenario=request.scenario,
        signal_id=request.signal_id,
        log_dir=get_log_dir(use_env=True),
        persist=True,
    )


@app.get("/live/funding-readiness/status")
def live_funding_readiness_status() -> dict:
    return build_funded_tiny_live_readiness_status(log_dir=get_log_dir(use_env=True))


@app.get("/live/funding-readiness/runbook")
def live_funding_readiness_runbook() -> dict:
    return build_funded_tiny_live_readiness_runbook(log_dir=get_log_dir(use_env=True))


@app.post("/live/funding-readiness/check")
def live_funding_readiness_check() -> dict:
    return build_funded_tiny_live_readiness_check(log_dir=get_log_dir(use_env=True))


@app.get("/live/funding-balance/status")
def live_funding_balance_status() -> dict:
    return build_post_funding_balance_status(log_dir=get_log_dir(use_env=True))


@app.get("/live/funding-balance/runbook")
def live_funding_balance_runbook() -> dict:
    return build_post_funding_balance_runbook()


@app.post("/live/funding-balance/check")
def live_funding_balance_check(request: PostFundingBalanceRequest | None = None) -> dict:
    request = request or PostFundingBalanceRequest()
    return evaluate_and_record_post_funding_balance_check(
        available_usdt=request.available_usdt,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/live/rehearsal-readiness/status")
def live_rehearsal_readiness_status(detail: str = Query(default="fast")) -> dict:
    return build_rehearsal_test_order_protective_status(log_dir=get_log_dir(use_env=True), detail=detail)


@app.get("/live/rehearsal-readiness/runbook")
def live_rehearsal_readiness_runbook() -> dict:
    return build_rehearsal_test_order_protective_runbook(log_dir=get_log_dir(use_env=True))


@app.post("/live/rehearsal-readiness/check")
def live_rehearsal_readiness_check(
    request: RehearsalTestOrderProtectiveReadinessRequest | None = None,
    detail: str = Query(default="fast"),
) -> dict:
    request = request or RehearsalTestOrderProtectiveReadinessRequest()
    return build_rehearsal_test_order_protective_check(
        signal_id=request.signal_id,
        execution_intent_id=request.execution_intent_id,
        available_usdt=request.available_usdt,
        log_dir=get_log_dir(use_env=True),
        detail=detail,
    )


@app.get("/live/operator-performance/status")
def live_operator_performance_status() -> dict:
    return {
        "status": "OK",
        "phase": "R78.1",
        "system": "money_printing_machine_hammer_radar",
        "execution_mode": "PERFORMANCE_HOTFIX_ONLY",
        "recent_routes": [
            "/live/rehearsal-readiness/status",
            "/live/rehearsal-readiness/check",
            "/telegram/operator-command FIRST LIVE NEXT",
        ],
        "notes": [
            "Use curl --max-time 5 for operator endpoints",
            "R78 default mode is fast",
        ],
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "network_allowed": False,
        "secrets_shown": False,
    }


@app.get("/live/final-gate/status")
def live_final_gate_status() -> dict:
    return build_final_protected_live_gate_status(log_dir=get_log_dir(use_env=True))


@app.get("/live/final-gate/runbook")
def live_final_gate_runbook() -> dict:
    return build_final_protected_live_gate_runbook(log_dir=get_log_dir(use_env=True))


@app.post("/live/final-gate/check")
def live_final_gate_check(request: FinalProtectedLiveGateRequest | None = None) -> dict:
    request = request or FinalProtectedLiveGateRequest()
    return build_final_protected_live_gate_check(
        available_usdt=request.available_usdt,
        signal_id=request.signal_id,
        execution_intent_id=request.execution_intent_id,
        log_dir=get_log_dir(use_env=True),
    )


@app.post("/live/first-candidates/select")
def first_live_candidates_select(request: FirstLiveCandidateSelectRequest) -> dict:
    return select_first_live_candidate(
        signal_id=request.signal_id,
        source=request.source,
        reason=request.reason,
        log_dir=get_log_dir(use_env=True),
    )


@app.post("/live/first-candidates/clear")
def first_live_candidates_clear(request: FirstLiveCandidateClearRequest | None = None) -> dict:
    request = request or FirstLiveCandidateClearRequest()
    return clear_selected_signal(
        source=request.source,
        reason=request.reason,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/live/arming/runbook")
def live_arming_runbook() -> dict:
    return build_live_arming_runbook(log_dir=get_log_dir(use_env=True))


@app.post("/live/arming/runbook/check")
def live_arming_runbook_check() -> dict:
    return evaluate_and_record_live_arming_runbook(log_dir=get_log_dir(use_env=True))


@app.get("/live/arming/runbooks")
def live_arming_runbooks(limit: int = Query(default=20, ge=0), status: str | None = None) -> dict:
    return list_live_arming_runbooks(limit=limit, status=status, log_dir=get_log_dir(use_env=True))


@app.post("/live-connector/stub-submit")
def live_connector_stub_submit(request: LiveConnectorSubmitRequest) -> dict:
    return submit_live_order_stub(
        ticket_id=request.ticket_id,
        operator=request.operator,
        notes=request.notes,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/live-connector/attempts")
def live_connector_attempts(
    limit: int = Query(default=50, ge=0),
    signal_id: str | None = None,
    ticket_id: str | None = None,
) -> dict:
    records = load_live_attempts(limit=limit, signal_id=signal_id, ticket_id=ticket_id, log_dir=get_log_dir(use_env=True))
    return {
        "connector_mode": CONNECTOR_MODE,
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "live_attempts": records,
    }


@app.get("/binance-readonly/status")
def binance_readonly_status() -> dict:
    return build_binance_readonly_status()


@app.get("/binance-readonly/exchange-info")
def binance_readonly_exchange_info(symbol: str = "BTCUSDT") -> dict:
    return build_binance_exchange_info(symbol=symbol)


@app.get("/binance-live/status")
def binance_live_status() -> dict:
    return build_binance_live_status()


@app.get("/binance-live/connector-status")
def binance_live_connector_status() -> dict:
    return build_connector_status(log_dir=get_log_dir(use_env=True))


@app.post("/binance-live/payload-preview")
def binance_live_payload_preview() -> dict:
    return preview_payload(log_dir=get_log_dir(use_env=True))


@app.post("/binance-live/test-order")
def binance_live_test_order(request: BinanceLiveTestOrderRequest | None = None) -> dict:
    request = request or BinanceLiveTestOrderRequest()
    return submit_test_order(
        log_dir=get_log_dir(use_env=True),
        use_mock_adapter=request.use_mock_adapter,
        require_exact_approval=request.require_exact_approval,
    )


@app.get("/binance-live/protective-status")
def binance_live_protective_status() -> dict:
    return build_protective_status(log_dir=get_log_dir(use_env=True))


@app.post("/binance-live/protective-preview")
def binance_live_protective_preview() -> dict:
    return protective_preview(log_dir=get_log_dir(use_env=True))


@app.post("/binance-live/protective-test")
def binance_live_protective_test(request: BinanceProtectiveRequest | None = None) -> dict:
    request = request or BinanceProtectiveRequest()
    return submit_protective_test(log_dir=get_log_dir(use_env=True), use_mock_adapter=request.use_mock_adapter)


@app.post("/binance-live/execute")
def binance_live_execute(request: BinanceLiveExecuteRequest | None = None) -> dict:
    request = request or BinanceLiveExecuteRequest()
    return execute_live_order(
        log_dir=get_log_dir(use_env=True),
        signal_id=request.signal_id,
        use_mock_adapter=request.use_mock_adapter,
        require_test_order_first=request.require_test_order_first,
        require_protective_orders=request.require_protective_orders,
    )


@app.get("/binance-live/connector-attempts")
def binance_live_connector_attempts(limit: int = Query(default=50, ge=0), signal_id: str | None = None) -> dict:
    log_dir = get_log_dir(use_env=True)
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "allow_live_orders": False,
        "global_kill_switch": True,
        "order_placed": ORDER_PLACED,
        "execution_attempted": False,
        "order_payload_created": False,
        "signed_payload_created": False,
        "secrets_shown": False,
        "binance_live_connector_attempts_path": str(connector_attempts_path(log_dir)),
        "binance_live_connector_attempts": load_connector_attempts(
            limit=limit,
            signal_id=signal_id,
            log_dir=log_dir,
        ),
    }


@app.get("/binance-live/protective-attempts")
def binance_live_protective_attempts(limit: int = Query(default=50, ge=0), signal_id: str | None = None) -> dict:
    log_dir = get_log_dir(use_env=True)
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "allow_live_orders": False,
        "global_kill_switch": True,
        "order_placed": ORDER_PLACED,
        "real_order_placed": False,
        "protective_orders_sent": False,
        "execution_attempted": False,
        "order_payload_created": False,
        "signed_payload_created": False,
        "secrets_shown": False,
        "binance_protective_order_attempts_path": str(protective_attempts_path(log_dir)),
        "binance_protective_order_attempts": load_protective_attempts(
            limit=limit,
            signal_id=signal_id,
            log_dir=log_dir,
        ),
    }


@app.get("/betrayal-shadow/outcomes")
def betrayal_shadow_outcomes(
    limit: int = Query(default=50, ge=0),
    status: str | None = None,
    symbol: str | None = None,
) -> dict:
    return build_betrayal_shadow_outcomes_payload(
        limit=limit,
        status=status,
        symbol=symbol,
        log_dir=get_log_dir(use_env=True),
    )


@app.post("/betrayal-shadow/track")
def betrayal_shadow_track(request: BetrayalShadowTrackRequest | None = None) -> dict:
    request = request or BetrayalShadowTrackRequest()
    return track_betrayal_shadow_outcomes(
        latest_only=request.latest_only,
        limit=request.limit,
        since_hours=request.since_hours,
        symbol=request.symbol,
        min_betrayal_score=request.min_betrayal_score,
        log_dir=get_log_dir(use_env=True),
    )


@app.post("/betrayal-shadow/resolve")
def betrayal_shadow_resolve(request: BetrayalShadowResolveRequest | None = None) -> dict:
    request = request or BetrayalShadowResolveRequest()
    return resolve_betrayal_shadow_outcomes(
        limit=request.limit,
        symbol=request.symbol,
        timeframe=request.timeframe,
        dry_run=request.dry_run,
        write=request.write,
        since_hours=request.since_hours,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/betrayal-shadow/resolutions")
def betrayal_shadow_resolutions(
    limit: int = Query(default=50, ge=0),
    symbol: str | None = None,
    timeframe: str | None = None,
) -> dict:
    return build_betrayal_shadow_resolutions_payload(
        limit=limit,
        symbol=symbol,
        timeframe=timeframe,
        log_dir=get_log_dir(use_env=True),
    )


@app.post("/betrayal-shadow/candle-archive/build")
def betrayal_shadow_candle_archive_build(request: BetrayalCandleArchiveRequest | None = None) -> dict:
    request = request or BetrayalCandleArchiveRequest()
    return build_betrayal_candle_archive(
        dry_run=request.dry_run,
        write=request.write,
        symbol=request.symbol,
        timeframe=request.timeframe,
        limit=request.limit,
        since_hours=request.since_hours,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/betrayal-shadow/candle-archive/status")
def betrayal_shadow_candle_archive_status(
    symbol: str | None = None,
    timeframe: str | None = None,
) -> dict:
    return build_betrayal_candle_archive_status(
        symbol=symbol,
        timeframe=timeframe,
        log_dir=get_log_dir(use_env=True),
    )


@app.post("/betrayal-shadow/candle-capture/backfill")
def betrayal_shadow_candle_capture_backfill(request: BetrayalCandleCaptureRequest | None = None) -> dict:
    request = request or BetrayalCandleCaptureRequest()
    return backfill_betrayal_candle_capture(
        dry_run=request.dry_run,
        write=request.write,
        symbol=request.symbol,
        timeframe=request.timeframe,
        limit=request.limit,
        since_hours=request.since_hours,
        source_mode=request.source_mode,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/betrayal-shadow/candle-capture/status")
def betrayal_shadow_candle_capture_status(
    symbol: str | None = None,
    timeframe: str | None = None,
) -> dict:
    return build_betrayal_candle_capture_status(
        symbol=symbol,
        timeframe=timeframe,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/notifications/status")
def notifications_status() -> dict:
    return notification_status(log_dir=get_log_dir(use_env=True))


@app.post("/notifications/check")
def notifications_check(request: NotificationCheckRequest | None = None) -> dict:
    request = request or NotificationCheckRequest()
    return check_notifications(
        send=request.send,
        channel=request.channel,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/notifications/alerts")
def notifications_alerts(limit: int = Query(default=50, ge=0)) -> dict:
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "readiness_alerts": load_alert_records(limit=limit, log_dir=get_log_dir(use_env=True)),
    }


@app.get("/strategy-performance/summary")
def strategy_performance_summary() -> dict:
    return build_strategy_performance_summary(log_dir=get_log_dir(use_env=True))


@app.get("/strategy-performance/timeframes")
def strategy_performance_timeframes() -> dict:
    return build_strategy_timeframe_summary(log_dir=get_log_dir(use_env=True))


@app.get("/strategy-performance/entry-modes")
def strategy_performance_entry_modes() -> dict:
    return build_strategy_entry_mode_summary(log_dir=get_log_dir(use_env=True))


@app.get("/strategy-performance/live-eligibility")
def strategy_performance_live_eligibility() -> dict:
    return build_live_eligibility_matrix(log_dir=get_log_dir(use_env=True))


@app.get("/strategy-performance/betrayal-audit")
def strategy_performance_betrayal_audit() -> dict:
    return build_betrayal_strategy_audit(log_dir=get_log_dir(use_env=True))


@app.get("/strategy-performance/betrayal-inverse-validation")
def strategy_performance_betrayal_inverse_validation() -> dict:
    return build_betrayal_inverse_validation(log_dir=get_log_dir(use_env=True))


@app.get("/strategy-performance/markov-regime-gate")
def strategy_performance_markov_regime_gate(
    symbol: str = "BTCUSDT",
    timeframe: str | None = None,
    limit: int = Query(default=120, ge=0),
) -> dict:
    return build_markov_regime_gate(
        symbol=symbol,
        timeframe=timeframe,
        limit=limit,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/strategy-performance/miro-fish-quality-gate")
def strategy_performance_miro_fish_quality_gate(
    symbol: str = "BTCUSDT",
    timeframe: str | None = None,
    family: str | None = None,
    limit: int = Query(default=120, ge=0),
) -> dict:
    return build_miro_fish_quality_gate(
        symbol=symbol,
        timeframe=timeframe,
        family=family,
        limit=limit,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/live-arming/preflight")
def live_arming_preflight(
    symbol: str = "BTCUSDT",
    timeframe: str | None = None,
    candidate_id: str | None = None,
) -> dict:
    return build_live_arming_preflight(
        symbol=symbol,
        timeframe=timeframe,
        candidate_id=candidate_id,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/live-arming/risk-contract")
def live_arming_risk_contract(
    candidate_id: str = "normal|BTCUSDT|13m|long|ladder_close_50_618",
) -> dict:
    return build_tiny_live_risk_contract_payload(candidate_id=candidate_id)


@app.post("/live-arming/ticket/build")
def live_arming_ticket_build(request: TinyLiveTicketBuildRequest | None = None) -> dict:
    request = request or TinyLiveTicketBuildRequest()
    return build_tiny_live_ticket(
        candidate_id=request.candidate_id or "normal|BTCUSDT|13m|long|ladder_close_50_618",
        approval_phrase=request.approval_phrase,
        operator_note=request.operator_note,
        dry_run=request.dry_run,
        write=request.write,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/live-arming/tickets")
def live_arming_tickets(
    limit: int = Query(default=20, ge=0),
    candidate_id: str | None = None,
) -> dict:
    return build_tiny_live_tickets_payload(limit=limit, candidate_id=candidate_id, log_dir=get_log_dir(use_env=True))


@app.post("/live-arming/checklist/confirm")
def live_arming_checklist_confirm(request: LiveEnvChecklistConfirmRequest | None = None) -> dict:
    request = request or LiveEnvChecklistConfirmRequest()
    return build_live_env_arming_checklist(
        candidate_id=request.candidate_id or "normal|BTCUSDT|13m|long|ladder_close_50_618",
        risk_contract_hash=request.risk_contract_hash,
        manual_funding_phrase=request.manual_funding_phrase,
        live_env_review_phrase=request.live_env_review_phrase,
        max_loss_ack_phrase=request.max_loss_ack_phrase,
        exact_candidate_ack_phrase=request.exact_candidate_ack_phrase,
        operator_note=request.operator_note,
        dry_run=request.dry_run,
        write=request.write,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/live-arming/checklist/status")
def live_arming_checklist_status(
    candidate_id: str = "normal|BTCUSDT|13m|long|ladder_close_50_618",
    limit: int = Query(default=20, ge=0),
) -> dict:
    return build_live_env_arming_checklist_status(candidate_id=candidate_id, limit=limit, log_dir=get_log_dir(use_env=True))


@app.get("/live-arming/env-boundary-review")
def live_arming_env_boundary_review(
    candidate_id: str = "normal|BTCUSDT|13m|long|ladder_close_50_618",
) -> dict:
    return build_live_env_boundary_review(candidate_id=candidate_id, dry_run=True, write=False, log_dir=get_log_dir(use_env=True))


@app.post("/live-arming/env-boundary-review/report")
def live_arming_env_boundary_review_report(request: LiveEnvBoundaryReviewReportRequest | None = None) -> dict:
    request = request or LiveEnvBoundaryReviewReportRequest()
    return build_live_env_boundary_review(
        candidate_id=request.candidate_id or "normal|BTCUSDT|13m|long|ladder_close_50_618",
        dry_run=request.dry_run,
        write=request.write,
        log_dir=get_log_dir(use_env=True),
    )


@app.post("/live-arming/review-packet/build")
def live_arming_review_packet_build(request: FinalHumanReviewPacketBuildRequest | None = None) -> dict:
    request = request or FinalHumanReviewPacketBuildRequest()
    return build_final_human_review_packet(
        candidate_id=request.candidate_id or "normal|BTCUSDT|13m|long|ladder_close_50_618",
        final_approval_phrase=request.final_approval_phrase,
        operator_note=request.operator_note,
        dry_run=request.dry_run,
        write=request.write,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/live-arming/review-packets")
def live_arming_review_packets(
    limit: int = Query(default=20, ge=0),
    candidate_id: str | None = None,
) -> dict:
    return build_final_human_review_packets_payload(limit=limit, candidate_id=candidate_id, log_dir=get_log_dir(use_env=True))


@app.post("/live-arming/human-confirmations/record")
def live_arming_human_confirmations_record(request: HumanConfirmationRecordRequest | None = None) -> dict:
    request = request or HumanConfirmationRecordRequest()
    return build_human_confirmation_records(
        candidate_id=request.candidate_id or "normal|BTCUSDT|13m|long|ladder_close_50_618",
        r85_approval_phrase=request.r85_approval_phrase,
        r86_manual_funding_phrase=request.r86_manual_funding_phrase,
        r86_live_env_review_phrase=request.r86_live_env_review_phrase,
        r86_max_loss_ack_phrase=request.r86_max_loss_ack_phrase,
        r86_exact_candidate_ack_phrase=request.r86_exact_candidate_ack_phrase,
        r88_final_approval_phrase=request.r88_final_approval_phrase,
        operator_note=request.operator_note,
        dry_run=request.dry_run,
        write=request.write,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/live-arming/human-confirmations/status")
def live_arming_human_confirmations_status(
    candidate_id: str = "normal|BTCUSDT|13m|long|ladder_close_50_618",
    limit: int = Query(default=20, ge=0),
) -> dict:
    return build_human_confirmation_records_status(candidate_id=candidate_id, limit=limit, log_dir=get_log_dir(use_env=True))


@app.get("/live-arming/human-confirmations")
def live_arming_human_confirmations(
    candidate_id: str = "normal|BTCUSDT|13m|long|ladder_close_50_618",
    limit: int = Query(default=20, ge=0),
) -> dict:
    return build_human_confirmation_records_status(candidate_id=candidate_id, limit=limit, log_dir=get_log_dir(use_env=True))


@app.get("/live-arming/readiness-snapshot")
def live_arming_readiness_snapshot(
    candidate_id: str = "normal|BTCUSDT|13m|long|ladder_close_50_618",
) -> dict:
    return build_review_record_arming_snapshot(
        candidate_id=candidate_id,
        dry_run=True,
        write=False,
        log_dir=get_log_dir(use_env=True),
    )


@app.post("/live-arming/readiness-snapshot/report")
def live_arming_readiness_snapshot_report(request: ReadinessSnapshotReportRequest | None = None) -> dict:
    request = request or ReadinessSnapshotReportRequest()
    return build_review_record_arming_snapshot(
        candidate_id=request.candidate_id or "normal|BTCUSDT|13m|long|ladder_close_50_618",
        dry_run=request.dry_run,
        write=request.write,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/live-arming/source-warning-review")
def live_arming_source_warning_review(
    candidate_id: str = "normal|BTCUSDT|13m|long|ladder_close_50_618",
) -> dict:
    return build_source_warning_review(
        candidate_id=candidate_id,
        dry_run=True,
        write=False,
        log_dir=get_log_dir(use_env=True),
    )


@app.post("/live-arming/source-warning-review/report")
def live_arming_source_warning_review_report(request: SourceWarningReviewReportRequest | None = None) -> dict:
    request = request or SourceWarningReviewReportRequest()
    return build_source_warning_review(
        candidate_id=request.candidate_id or "normal|BTCUSDT|13m|long|ladder_close_50_618",
        dry_run=request.dry_run,
        write=request.write,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/live-arming/source-chain-repair")
def live_arming_source_chain_repair(
    candidate_id: str = "normal|BTCUSDT|13m|long|ladder_close_50_618",
) -> dict:
    return build_source_chain_repair(
        candidate_id=candidate_id,
        dry_run=True,
        write=False,
        log_dir=get_log_dir(use_env=True),
    )


@app.post("/live-arming/source-chain-repair/report")
def live_arming_source_chain_repair_report(request: SourceChainRepairReportRequest | None = None) -> dict:
    request = request or SourceChainRepairReportRequest()
    return build_source_chain_repair(
        candidate_id=request.candidate_id or "normal|BTCUSDT|13m|long|ladder_close_50_618",
        dry_run=request.dry_run,
        write=request.write,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/live-arming/candidate-revalidation-watch")
def live_arming_candidate_revalidation_watch(
    candidate_id: str = "normal|BTCUSDT|13m|long|ladder_close_50_618",
) -> dict:
    return build_candidate_revalidation_watch(
        candidate_id=candidate_id,
        dry_run=True,
        write=False,
        log_dir=get_log_dir(use_env=True),
    )


@app.post("/live-arming/candidate-revalidation-watch/report")
def live_arming_candidate_revalidation_watch_report(
    request: CandidateRevalidationWatchReportRequest | None = None,
) -> dict:
    request = request or CandidateRevalidationWatchReportRequest()
    return build_candidate_revalidation_watch(
        candidate_id=request.candidate_id or "normal|BTCUSDT|13m|long|ladder_close_50_618",
        dry_run=request.dry_run,
        write=request.write,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/live-arming/dual-lane-candidate-watch")
def live_arming_dual_lane_candidate_watch(
    candidate_id: str = "normal|BTCUSDT|13m|long|ladder_close_50_618",
) -> dict:
    return build_dual_lane_candidate_watch(
        candidate_id=candidate_id,
        dry_run=True,
        write=False,
        log_dir=get_log_dir(use_env=True),
    )


@app.post("/live-arming/dual-lane-candidate-watch/report")
def live_arming_dual_lane_candidate_watch_report(
    request: DualLaneCandidateWatchReportRequest | None = None,
) -> dict:
    request = request or DualLaneCandidateWatchReportRequest()
    return build_dual_lane_candidate_watch(
        candidate_id=request.candidate_id or "normal|BTCUSDT|13m|long|ladder_close_50_618",
        dry_run=request.dry_run,
        write=request.write,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/live-arming/betrayal-true-paper-scaffold")
def live_arming_betrayal_true_paper_scaffold(
    symbol: str = "BTCUSDT",
    max_candidates: int = Query(default=20, ge=0),
) -> dict:
    return build_betrayal_true_paper_scaffold(
        symbol=symbol,
        max_candidates=max_candidates,
        dry_run=True,
        write=False,
        log_dir=get_log_dir(use_env=True),
    )


@app.post("/live-arming/betrayal-true-paper-scaffold/report")
def live_arming_betrayal_true_paper_scaffold_report(
    request: BetrayalTruePaperScaffoldReportRequest | None = None,
) -> dict:
    request = request or BetrayalTruePaperScaffoldReportRequest()
    return build_betrayal_true_paper_scaffold(
        symbol=request.symbol or "BTCUSDT",
        max_candidates=request.max_candidates if request.max_candidates is not None else 20,
        dry_run=request.dry_run,
        write=request.write,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/live-arming/betrayal-paper-outcomes/status")
def live_arming_betrayal_paper_outcomes_status(
    signal_id: str | None = None,
    recent: int = Query(default=20, ge=0),
) -> dict:
    return build_betrayal_paper_outcome_status(
        signal_id=signal_id,
        recent=recent,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/live-arming/betrayal-paper-outcomes")
def live_arming_betrayal_paper_outcomes(
    signal_id: str | None = None,
    recent: int = Query(default=20, ge=0),
) -> dict:
    return build_betrayal_paper_outcome_status(
        signal_id=signal_id,
        recent=recent,
        log_dir=get_log_dir(use_env=True),
    )


@app.post("/live-arming/betrayal-paper-outcomes/record")
def live_arming_betrayal_paper_outcomes_record(
    request: BetrayalPaperOutcomeRecordRequest | None = None,
) -> dict:
    request = request or BetrayalPaperOutcomeRecordRequest()
    return record_betrayal_paper_outcome(
        outcome=request.outcome,
        dry_run=request.dry_run,
        write=request.write,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/live-arming/betrayal-paper-signal-detector/status")
def live_arming_betrayal_paper_signal_detector_status(
    max_signals: int = Query(default=20, ge=0),
    identity_filter: str | None = None,
) -> dict:
    return build_betrayal_paper_signal_detector_status(
        max_signals=max_signals,
        identity_filter=identity_filter,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/live-arming/betrayal-paper-signal-detector/detections")
def live_arming_betrayal_paper_signal_detector_detections(
    max_signals: int = Query(default=20, ge=0),
    identity_filter: str | None = None,
) -> dict:
    return build_betrayal_paper_signal_detector_status(
        max_signals=max_signals,
        identity_filter=identity_filter,
        log_dir=get_log_dir(use_env=True),
    )


@app.post("/live-arming/betrayal-paper-signal-detector/run")
def live_arming_betrayal_paper_signal_detector_run(
    request: BetrayalPaperSignalDetectorRunRequest | None = None,
) -> dict:
    request = request or BetrayalPaperSignalDetectorRunRequest()
    return run_betrayal_paper_signal_detector(
        dry_run=request.dry_run,
        write=request.write,
        max_signals=request.max_signals if request.max_signals is not None else 20,
        identity_filter=request.identity_filter,
        allow_open_tracking=request.allow_open_tracking,
        allow_closed_outcomes=request.allow_closed_outcomes,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/live-arming/betrayal-detector-source-wiring")
def live_arming_betrayal_detector_source_wiring(
    symbol: str = "BTCUSDT",
    timeframe: str | None = "222m",
) -> dict:
    return build_betrayal_detector_source_wiring(
        symbol=symbol,
        timeframe=timeframe,
        dry_run=True,
        write=False,
        log_dir=get_log_dir(use_env=True),
    )


@app.post("/live-arming/betrayal-detector-source-wiring/report")
def live_arming_betrayal_detector_source_wiring_report(
    request: BetrayalDetectorSourceWiringReportRequest | None = None,
) -> dict:
    request = request or BetrayalDetectorSourceWiringReportRequest()
    return build_betrayal_detector_source_wiring(
        symbol=request.symbol or "BTCUSDT",
        timeframe=request.timeframe if request.timeframe is not None else "222m",
        dry_run=request.dry_run,
        write=request.write,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/live-arming/betrayal-source-signal-emitter/status")
def live_arming_betrayal_source_signal_emitter_status(
    max_signals: int = Query(default=20, ge=0),
    identity_filter: str | None = None,
) -> dict:
    return build_betrayal_source_signal_emitter_status(
        max_signals=max_signals,
        identity_filter=identity_filter,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/live-arming/betrayal-source-signal-emitter/signals")
def live_arming_betrayal_source_signal_emitter_signals(
    recent: int = Query(default=20, ge=0),
) -> dict:
    return {
        "status": "OK",
        "phase": "R100",
        "execution_mode": "BETRAYAL_SOURCE_SIGNAL_EMITTER_ONLY_NO_ORDER",
        "records": load_emitted_betrayal_paper_signals(limit=recent, log_dir=get_log_dir(use_env=True)),
        "review_only": True,
        "executable": False,
        "live_execution_enabled": False,
        "allow_live_orders": False,
        "global_kill_switch": True,
        "order_placed": False,
        "real_order_placed": False,
        "order_payload_created": False,
        "execution_attempted": False,
        "network_allowed": False,
        "secrets_shown": False,
    }


@app.post("/live-arming/betrayal-source-signal-emitter/run")
def live_arming_betrayal_source_signal_emitter_run(
    request: BetrayalSourceSignalEmitterRunRequest | None = None,
) -> dict:
    request = request or BetrayalSourceSignalEmitterRunRequest()
    return run_betrayal_source_signal_emitter(
        dry_run=request.dry_run,
        write=request.write,
        max_signals=request.max_signals if request.max_signals is not None else 20,
        identity_filter=request.identity_filter,
        allow_historical_replay=request.allow_historical_replay,
        allow_fresh_current=request.allow_fresh_current,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/strategy-promotion/status")
def strategy_promotion_status() -> dict:
    return build_strategy_promotion_status(log_dir=get_log_dir(use_env=True))


@app.post("/strategy-promotion/check")
def strategy_promotion_check(request: StrategyPromotionCheckRequest | None = None) -> dict:
    request = request or StrategyPromotionCheckRequest()
    return check_strategy_promotions(log_dir=get_log_dir(use_env=True), record_blocked=request.record_blocked)


@app.get("/strategy-promotion/events")
def strategy_promotion_events(limit: int = Query(default=50, ge=0), strategy_key: str | None = None) -> dict:
    log_dir = get_log_dir(use_env=True)
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "allow_live_orders": False,
        "global_kill_switch": True,
        "order_placed": ORDER_PLACED,
        "execution_attempted": False,
        "order_payload_created": False,
        "secrets_shown": False,
        "strategy_promotion_events_path": str(strategy_promotion_events_path(log_dir)),
        "strategy_promotion_events": load_strategy_promotion_events(
            limit=limit,
            strategy_key=strategy_key,
            log_dir=log_dir,
        ),
    }


@app.get("/strategy-promotion/events/{event_id}")
def strategy_promotion_event_by_id(event_id: str) -> dict:
    log_dir = get_log_dir(use_env=True)
    records = load_strategy_promotion_events(limit=0, event_id=event_id, log_dir=log_dir)
    if not records:
        raise HTTPException(status_code=404, detail="strategy promotion event not found")
    record = dict(records[0])
    record["live_execution_enabled"] = LIVE_EXECUTION_ENABLED
    record["allow_live_orders"] = False
    record["global_kill_switch"] = True
    record["order_placed"] = ORDER_PLACED
    record["execution_attempted"] = False
    record["order_payload_created"] = False
    record["secrets_shown"] = False
    record["strategy_promotion_events_path"] = str(strategy_promotion_events_path(log_dir))
    return record


@app.get("/live-preflight/promoted-strategy")
def live_preflight_promoted_strategy() -> dict:
    return build_promoted_strategy_preflight(log_dir=get_log_dir(use_env=True))


@app.post("/live-preflight/evaluate")
def live_preflight_evaluate() -> dict:
    return evaluate_and_record_live_preflight(log_dir=get_log_dir(use_env=True))


@app.get("/live-preflight/packs")
def live_preflight_packs(
    limit: int = Query(default=50, ge=0),
    strategy_key: str | None = None,
) -> dict:
    log_dir = get_log_dir(use_env=True)
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "allow_live_orders": False,
        "global_kill_switch": True,
        "order_placed": ORDER_PLACED,
        "execution_attempted": False,
        "order_payload_created": False,
        "secrets_shown": False,
        "live_preflight_packs_path": str(live_preflight_packs_path(log_dir)),
        "live_preflight_packs": load_live_preflight_packs(
            limit=limit,
            strategy_key=strategy_key,
            log_dir=log_dir,
        ),
    }


@app.get("/live-preflight/packs/{preflight_id}")
def live_preflight_pack_by_id(preflight_id: str) -> dict:
    log_dir = get_log_dir(use_env=True)
    records = load_live_preflight_packs(limit=0, preflight_id=preflight_id, log_dir=log_dir)
    if not records:
        raise HTTPException(status_code=404, detail="live preflight pack not found")
    record = dict(records[0])
    record["live_execution_enabled"] = LIVE_EXECUTION_ENABLED
    record["allow_live_orders"] = False
    record["global_kill_switch"] = True
    record["order_placed"] = ORDER_PLACED
    record["execution_attempted"] = False
    record["order_payload_created"] = False
    record["secrets_shown"] = False
    record["live_preflight_packs_path"] = str(live_preflight_packs_path(log_dir))
    return record


@app.get("/first-live/runbook")
def first_live_runbook() -> dict:
    return build_first_live_runbook(log_dir=get_log_dir(use_env=True))


@app.post("/first-live/evaluate")
def first_live_evaluate() -> dict:
    return evaluate_first_live_runbook(log_dir=get_log_dir(use_env=True))


@app.get("/first-live/evaluations")
def first_live_evaluations(limit: int = Query(default=50, ge=0), signal_id: str | None = None) -> dict:
    log_dir = get_log_dir(use_env=True)
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "allow_live_orders": False,
        "global_kill_switch": True,
        "order_placed": ORDER_PLACED,
        "real_order_placed": False,
        "secrets_shown": False,
        "first_live_runbook_evaluations_path": str(first_live_runbook_evaluations_path(log_dir)),
        "first_live_runbook_evaluations": load_first_live_runbook_evaluations(
            limit=limit,
            signal_id=signal_id,
            log_dir=log_dir,
        ),
    }


@app.get("/first-live/evaluations/{evaluation_id}")
def first_live_evaluation_by_id(evaluation_id: str) -> dict:
    log_dir = get_log_dir(use_env=True)
    records = load_first_live_runbook_evaluations(limit=0, evaluation_id=evaluation_id, log_dir=log_dir)
    if not records:
        raise HTTPException(status_code=404, detail="first live runbook evaluation not found")
    record = dict(records[0])
    record["live_execution_enabled"] = LIVE_EXECUTION_ENABLED
    record["allow_live_orders"] = False
    record["global_kill_switch"] = True
    record["order_placed"] = ORDER_PLACED
    record["real_order_placed"] = False
    record["secrets_shown"] = False
    record["first_live_runbook_evaluations_path"] = str(first_live_runbook_evaluations_path(log_dir))
    return record


@app.post("/telegram/operator-command")
def telegram_operator_command(request: TelegramOperatorCommandRequest) -> dict:
    return handle_telegram_operator_command(
        text=request.text,
        source=request.source,
        chat_id=request.chat_id,
        update_id=request.update_id,
        log_dir=get_log_dir(use_env=True),
    )


@app.post("/telegram/first-live/challenge")
def telegram_first_live_challenge() -> dict:
    return create_first_live_approval_challenge(log_dir=get_log_dir(use_env=True))


@app.post("/telegram/first-live/reply")
def telegram_first_live_reply(request: TelegramChallengeReplyRequest) -> dict:
    return process_first_live_challenge_reply(
        text=request.text,
        source=request.source,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/telegram/first-live/challenges")
def telegram_first_live_challenges(limit: int = Query(default=50, ge=0), signal_id: str | None = None) -> dict:
    log_dir = get_log_dir(use_env=True)
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "allow_live_orders": False,
        "global_kill_switch": True,
        "order_placed": ORDER_PLACED,
        "real_order_placed": False,
        "execution_attempted": False,
        "secrets_shown": False,
        "telegram_approval_challenges_path": str(telegram_approval_challenges_path(log_dir)),
        "telegram_approval_challenges": load_telegram_approval_challenges(
            limit=limit,
            signal_id=signal_id,
            log_dir=log_dir,
        ),
    }


@app.get("/telegram/first-live/challenges/{challenge_id}")
def telegram_first_live_challenge_by_id(challenge_id: str) -> dict:
    log_dir = get_log_dir(use_env=True)
    records = load_telegram_approval_challenges(limit=0, challenge_id=challenge_id, log_dir=log_dir)
    if not records:
        raise HTTPException(status_code=404, detail="telegram approval challenge not found")
    record = dict(records[0])
    record["live_execution_enabled"] = LIVE_EXECUTION_ENABLED
    record["allow_live_orders"] = False
    record["global_kill_switch"] = True
    record["order_placed"] = ORDER_PLACED
    record["real_order_placed"] = False
    record["execution_attempted"] = False
    record["secrets_shown"] = False
    record["telegram_approval_challenges_path"] = str(telegram_approval_challenges_path(log_dir))
    return record


@app.get("/telegram/operator-commands")
def telegram_operator_commands(limit: int = Query(default=50, ge=0)) -> dict:
    log_dir = get_log_dir(use_env=True)
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "allow_live_orders": False,
        "global_kill_switch": True,
        "order_placed": ORDER_PLACED,
        "real_order_placed": False,
        "execution_attempted": False,
        "secrets_shown": False,
        "telegram_operator_commands_path": str(telegram_operator_commands_path(log_dir)),
        "telegram_operator_commands": load_telegram_operator_commands(limit=limit, log_dir=log_dir),
    }


@app.get("/telegram/polling/status")
def telegram_polling_status() -> dict:
    return polling_status(log_dir=get_log_dir(use_env=True))


@app.post("/telegram/polling/once")
def telegram_polling_once(request: TelegramPollingOnceRequest | None = None) -> dict:
    request = request or TelegramPollingOnceRequest()
    return poll_telegram_once(
        log_dir=get_log_dir(use_env=True),
        send_responses=request.send_responses,
        dry_run=request.dry_run,
        max_updates=request.max_updates,
    )


@app.get("/telegram/polling/state")
def telegram_polling_state() -> dict:
    return polling_state(log_dir=get_log_dir(use_env=True))


@app.post("/operator/parse-action")
def operator_parse_action(request: OperatorParseActionRequest) -> dict:
    return parse_operator_action(request.text, signal_id=request.signal_id)


@app.post("/operator/live-approval/evaluate")
def operator_live_approval_evaluate(request: LiveApprovalEvaluateRequest) -> dict:
    return evaluate_live_approval_request(
        text=request.text,
        source=request.source,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/operator/live-approval/requests")
def operator_live_approval_requests(limit: int = Query(default=50, ge=0), signal_id: str | None = None) -> dict:
    log_dir = get_log_dir(use_env=True)
    records = load_live_approval_requests(limit=limit, signal_id=signal_id, log_dir=log_dir)
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "allow_live_orders": False,
        "global_kill_switch": True,
        "order_placed": ORDER_PLACED,
        "real_order_placed": False,
        "execution_attempted": False,
        "order_payload_created": False,
        "secrets_shown": False,
        "count": len(records),
        "live_approval_requests_path": str(live_approval_requests_path(log_dir)),
        "live_approval_requests": records,
        "requests": records,
    }


@app.get("/operator/live-approval/requests/{request_id}")
def operator_live_approval_request_by_id(request_id: str) -> dict:
    log_dir = get_log_dir(use_env=True)
    records = load_live_approval_requests(limit=0, request_id=request_id, log_dir=log_dir)
    if not records:
        raise HTTPException(status_code=404, detail="live approval request not found")
    record = dict(records[0])
    record["live_execution_enabled"] = LIVE_EXECUTION_ENABLED
    record["allow_live_orders"] = False
    record["global_kill_switch"] = True
    record["order_placed"] = ORDER_PLACED
    record["execution_attempted"] = False
    record["order_payload_created"] = False
    record["live_approval_requests_path"] = str(live_approval_requests_path(log_dir))
    return record


@app.post("/operator/actions")
def create_operator_action(request: OperatorActionRequest) -> dict:
    log_dir = get_log_dir(use_env=True)
    parsed = parse_operator_action(request.text, signal_id=request.signal_id)
    candidate_snapshot = _operator_action_candidate_snapshot(
        signal_id=parsed.get("signal_id"),
        normalized_action=parsed["normalized_action"],
    )
    record = build_operator_action_record(
        text=request.text,
        source=request.source,
        signal_id=parsed.get("signal_id"),
        alert_id=request.alert_id,
        candidate_snapshot=candidate_snapshot,
    )
    append_operator_action(record, log_dir=log_dir)
    record["operator_actions_path"] = str(operator_actions_path(log_dir))
    if parsed["normalized_action"] == "live_approve_exact":
        gate = evaluate_live_approval_request(
            text=request.text,
            source=request.source,
            log_dir=log_dir,
        )
        gate["operator_action"] = record
        gate["operator_actions_path"] = str(operator_actions_path(log_dir))
        return gate
    if parsed["normalized_action"] == "first_live_check":
        runbook = evaluate_first_live_runbook(log_dir=log_dir)
        runbook["operator_action"] = record
        runbook["operator_actions_path"] = str(operator_actions_path(log_dir))
        return runbook
    if parsed["normalized_action"] == "telegram_operator_command":
        bridge = handle_telegram_operator_command(
            text=request.text,
            source=request.source,
            log_dir=log_dir,
        )
        bridge["operator_action"] = record
        bridge["operator_actions_path"] = str(operator_actions_path(log_dir))
        return bridge
    return record


@app.get("/operator/actions")
def operator_actions(limit: int = Query(default=50, ge=0), signal_id: str | None = None) -> dict:
    log_dir = get_log_dir(use_env=True)
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "operator_actions_path": str(operator_actions_path(log_dir)),
        "operator_actions": load_operator_actions(limit=limit, signal_id=signal_id, log_dir=log_dir),
    }


@app.get("/operator/actions/{action_id}")
def operator_action_by_id(action_id: str) -> dict:
    log_dir = get_log_dir(use_env=True)
    records = load_operator_actions(limit=0, action_id=action_id, log_dir=log_dir)
    if not records:
        raise HTTPException(status_code=404, detail="operator action not found")
    record = dict(records[0])
    record["live_execution_enabled"] = LIVE_EXECUTION_ENABLED
    record["order_placed"] = ORDER_PLACED
    record["operator_actions_path"] = str(operator_actions_path(log_dir))
    return record


@app.get("/operator/latest")
def operator_latest() -> dict:
    log_dir = get_log_dir(use_env=True)
    actions = load_operator_actions(limit=1, log_dir=log_dir)
    alerts = load_alert_records(limit=1, log_dir=log_dir)
    live_approval_requests = load_live_approval_requests(limit=1, log_dir=log_dir)
    live_preflight_packs = load_live_preflight_packs(limit=1, log_dir=log_dir)
    connector_attempts = load_connector_attempts(limit=1, log_dir=log_dir)
    first_live_evaluations = load_first_live_runbook_evaluations(limit=1, log_dir=log_dir)
    telegram_commands = load_telegram_operator_commands(limit=1, log_dir=log_dir)
    telegram_challenges = load_telegram_approval_challenges(limit=1, log_dir=log_dir)
    latest_candidate = _latest_candidate_snapshot()
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "allow_live_orders": False,
        "global_kill_switch": True,
        "order_placed": ORDER_PLACED,
        "latest_operator_action": actions[0] if actions else None,
        "latest_live_approval_request": live_approval_requests[0] if live_approval_requests else None,
        "latest_live_preflight_pack": live_preflight_packs[0] if live_preflight_packs else None,
        "latest_binance_live_connector_attempt": connector_attempts[0] if connector_attempts else None,
        "latest_first_live_runbook_evaluation": first_live_evaluations[0] if first_live_evaluations else None,
        "latest_telegram_operator_command": telegram_commands[0] if telegram_commands else None,
        "latest_telegram_approval_challenge": telegram_challenges[0] if telegram_challenges else None,
        "latest_alert": alerts[0] if alerts else None,
        "latest_candidate": latest_candidate,
    }


@app.get("/watchlist")
def watchlist(
    category: WatchlistCategory | None = None,
    include_disabled: bool = True,
    limit: int = Query(default=50, ge=0),
) -> dict:
    return build_watchlist(
        category=category,
        include_disabled=include_disabled,
        limit=limit,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/watchlist/summary")
def watchlist_summary() -> dict:
    return build_watchlist_summary(log_dir=get_log_dir(use_env=True))


@app.get("/multi-symbol/scan")
def multi_symbol_scan(
    symbol: str | None = None,
    category: WatchlistCategory | None = None,
    limit: int = Query(default=50, ge=0),
    write: bool = False,
) -> dict:
    return scan_watchlist(
        symbol=symbol,
        category=category,
        limit=limit,
        write=write,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/multi-symbol/scans")
def multi_symbol_scans(
    limit: int = Query(default=50, ge=0),
    symbol: str | None = None,
    category: WatchlistCategory | None = None,
    status: str | None = None,
) -> dict:
    return build_multi_symbol_scans_payload(
        limit=limit,
        symbol=symbol,
        category=category,
        status=status,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/multi-symbol/summary")
def multi_symbol_summary() -> dict:
    return build_multi_symbol_summary(log_dir=get_log_dir(use_env=True))


@app.get("/market-intelligence/summary")
def market_intelligence_summary(
    use_network: bool = False,
    write: bool = False,
    limit: int = Query(default=20, ge=0),
) -> dict:
    return build_market_intelligence_summary(
        use_network=use_network,
        write=write,
        limit=limit,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/market-intelligence/rankings")
def market_intelligence_rankings(
    use_network: bool = False,
    category: WatchlistCategory | None = None,
    limit: int = Query(default=20, ge=0),
) -> dict:
    return build_market_rankings(
        use_network=use_network,
        category=category,
        limit=limit,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/market-intelligence/rotation")
def market_intelligence_rotation(use_network: bool = False) -> dict:
    return evaluate_ethbtc_rotation(use_network=use_network, log_dir=get_log_dir(use_env=True))


@app.get("/market-intelligence/snapshots")
def market_intelligence_snapshots(limit: int = Query(default=50, ge=0)) -> dict:
    return build_market_snapshots_payload(limit=limit, log_dir=get_log_dir(use_env=True))


@app.get("/eth-paper/candidate")
def eth_paper_candidate(use_network: bool = False, write: bool = False) -> dict:
    return build_eth_paper_candidate(use_network=use_network, write=write, log_dir=get_log_dir(use_env=True))


@app.get("/eth-paper/candidates")
def eth_paper_candidates(limit: int = Query(default=50, ge=0), status: str | None = None) -> dict:
    return build_eth_candidates_payload(limit=limit, status=status, log_dir=get_log_dir(use_env=True))


@app.get("/eth-paper/summary")
def eth_paper_summary() -> dict:
    return build_eth_paper_summary(log_dir=get_log_dir(use_env=True))


@app.get("/eth-paper/outcome")
def eth_paper_outcome(candidate_id: str | None = None, write: bool = False) -> dict:
    return build_eth_paper_outcome(candidate_id=candidate_id, write=write, log_dir=get_log_dir(use_env=True))


@app.get("/eth-paper/outcomes")
def eth_paper_outcomes(
    limit: int = Query(default=50, ge=0),
    status: str | None = None,
    candidate_id: str | None = None,
) -> dict:
    return build_eth_paper_outcomes_payload(
        limit=limit,
        status=status,
        candidate_id=candidate_id,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/eth-paper/outcome-summary")
def eth_paper_outcome_summary() -> dict:
    return build_eth_paper_outcome_summary(log_dir=get_log_dir(use_env=True))


@app.get("/paper-refresh/status")
def paper_refresh_status() -> dict:
    return scheduler_status(log_dir=get_log_dir(use_env=True))


@app.post("/paper-refresh/run")
def paper_refresh_run(request: PaperRefreshRunRequest | None = None) -> dict:
    request = request or PaperRefreshRunRequest()
    return run_refresh_sequence(
        tasks=request.tasks,
        use_network=request.use_network,
        write_outputs=request.write_outputs,
        send_notifications=request.send_notifications,
        run_mode="API",
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/paper-refresh/runs")
def paper_refresh_runs(limit: int = Query(default=50, ge=0)) -> dict:
    return build_refresh_runs_payload(limit=limit, log_dir=get_log_dir(use_env=True))


@app.get("/candidates")
def candidates(
    limit: int = Query(default=10, ge=0),
    since_hours: int = Query(default=24, ge=0),
    fresh_minutes: int = Query(default=30, ge=0),
    max_position_usd: float = Query(default=DEFAULT_MAX_POSITION_USD, gt=0),
    max_risk_usd: float = Query(default=5.0, gt=0),
    max_leverage: float = Query(default=DEFAULT_MAX_LEVERAGE, ge=0),
    allow_short: bool = False,
    allow_oversold: bool = False,
    allow_trigger_flags: bool = False,
    latest_only: bool = False,
    symbol: str | None = None,
) -> dict:
    snapshot = build_live_candidate_snapshot(
        limit=limit,
        since_hours=since_hours,
        fresh_minutes=fresh_minutes,
        max_position_usd=max_position_usd,
        max_risk_usd=max_risk_usd,
        max_leverage=max_leverage,
        allow_short=allow_short,
        allow_oversold=allow_oversold,
        allow_trigger_flags=allow_trigger_flags,
        latest_only=latest_only,
    )
    return {
        "archive_log_dir": str(snapshot["archive_log_dir"]),
        "generated_at": snapshot["generated_at"].isoformat(),
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "candidates": [_candidate_snapshot(check) for check in snapshot["checks"]],
    }


@app.post("/decisions")
def create_decision(request: DecisionRequest) -> dict:
    log_dir = get_log_dir(use_env=True)
    candidate = _current_candidate_by_signal_id(request.signal_id)
    _validate_decision_request(request, candidate)
    record = {
        "decision_id": uuid4().hex,
        "created_at": datetime.now(UTC).isoformat(),
        "archive_log_dir": str(log_dir),
        "signal_id": request.signal_id,
        "decision": request.decision,
        "operator": request.operator,
        "notes": request.notes,
        "intended_position_usd": request.intended_position_usd,
        "intended_leverage": request.intended_leverage,
        "override_reason": request.override_reason,
        "candidate_snapshot": candidate,
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "source": "approval_api",
    }
    _append_decision(record, log_dir=log_dir)
    return record


@app.get("/decisions")
def decisions(limit: int = Query(default=50, ge=0), signal_id: str | None = None) -> dict:
    records = load_decisions(limit=limit, signal_id=signal_id, log_dir=get_log_dir(use_env=True))
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "decisions": records,
    }


@app.get("/decisions/{decision_id}")
def decision_by_id(decision_id: str) -> dict:
    for record in load_decisions(limit=0, log_dir=get_log_dir(use_env=True)):
        if record.get("decision_id") == decision_id:
            record = dict(record)
            record["live_execution_enabled"] = LIVE_EXECUTION_ENABLED
            record["order_placed"] = ORDER_PLACED
            return record
    raise HTTPException(status_code=404, detail="decision not found")


@app.post("/manual-outcomes")
def create_manual_outcome(request: ManualOutcomeRequest) -> dict:
    record = append_manual_outcome(
        signal_id=request.signal_id,
        result=request.result,
        entry_price=request.entry_price,
        exit_price=request.exit_price,
        position_usd=request.position_usd,
        leverage=request.leverage,
        pnl_usd=request.pnl_usd,
        pnl_pct=request.pnl_pct,
        notes=request.notes,
        log_dir=get_log_dir(use_env=True),
    )
    record["live_execution_enabled"] = LIVE_EXECUTION_ENABLED
    record["order_placed"] = ORDER_PLACED
    return record


@app.get("/manual-outcomes")
def manual_outcomes(limit: int = Query(default=50, ge=0), signal_id: str | None = None) -> dict:
    records = load_manual_outcomes(limit=limit, signal_id=signal_id, log_dir=get_log_dir(use_env=True))
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "manual_outcomes": records,
    }


def build_decisions_text(
    *,
    limit: int = 50,
    signal_id: str | None = None,
    log_dir: str | Path | None = None,
) -> str:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    records = load_decisions(limit=limit, signal_id=signal_id, log_dir=resolved_log_dir)
    lines = [
        "HAMMER RADAR MANUAL DECISIONS",
        f"archive_log_dir: {resolved_log_dir}",
        "live_execution_enabled: false",
        "order_placed: false",
    ]
    if not records:
        return "\n".join([*lines, "no manual decisions"])
    for record in records:
        lines.append(
            f"{record.get('created_at')} | {record.get('decision_id')} | signal={record.get('signal_id')} | "
            f"decision={record.get('decision')} | operator={record.get('operator')} | notes={record.get('notes', '')}"
        )
    return "\n".join(lines)


def load_decisions(
    *,
    limit: int = 50,
    signal_id: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict]:
    path = _decisions_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if signal_id is not None and record.get("signal_id") != signal_id:
                continue
            records.append(record)
    records = list(reversed(records))
    if limit > 0:
        return records[:limit]
    return records


def _current_candidate_by_signal_id(signal_id: str) -> dict | None:
    snapshot = build_live_candidate_snapshot(
        limit=1000,
        since_hours=24,
        fresh_minutes=30,
        max_position_usd=DEFAULT_MAX_POSITION_USD,
        max_risk_usd=5.0,
        max_leverage=DEFAULT_MAX_LEVERAGE,
    )
    for check in snapshot["checks"]:
        candidate = _candidate_snapshot(check)
        if candidate["signal_id"] == signal_id:
            return candidate
    return None


def _latest_candidate_snapshot() -> dict | None:
    snapshot = build_live_candidate_snapshot(
        limit=1,
        since_hours=24,
        fresh_minutes=30,
        max_position_usd=DEFAULT_MAX_POSITION_USD,
        max_risk_usd=5.0,
        max_leverage=DEFAULT_MAX_LEVERAGE,
    )
    if not snapshot["checks"]:
        return None
    return _candidate_snapshot(snapshot["checks"][0])


def _operator_action_candidate_snapshot(signal_id: str | None, normalized_action: str) -> dict | None:
    if signal_id:
        return _current_candidate_by_signal_id(signal_id)
    if normalized_action == "show_latest":
        return _latest_candidate_snapshot()
    return None


def _validate_decision_request(request: DecisionRequest, candidate: dict | None) -> None:
    if request.decision != "approve_manual_live":
        return
    if candidate is None:
        raise HTTPException(status_code=400, detail="approve_manual_live requires a current candidate")
    if candidate["decision"] == LIVE_DECISION_FORBIDDEN:
        raise HTTPException(status_code=400, detail="FORBIDDEN candidates cannot be approved")
    if candidate["decision"] != LIVE_DECISION_ELIGIBLE and not request.override_reason:
        raise HTTPException(status_code=400, detail="approval requires ELIGIBLE_TINY_LIVE or override_reason")
    if candidate["freshness_status"] == "expired" and not request.override_reason:
        raise HTTPException(status_code=400, detail="expired candidate approval requires override_reason")
    if (
        request.intended_position_usd is not None
        and request.intended_position_usd > DEFAULT_MAX_POSITION_USD
        and not request.override_reason
    ):
        raise HTTPException(status_code=400, detail="intended_position_usd exceeds default max_position_usd")
    if (
        request.intended_leverage is not None
        and request.intended_leverage > DEFAULT_MAX_LEVERAGE
        and not request.override_reason
    ):
        raise HTTPException(status_code=400, detail="intended_leverage exceeds default max_leverage")


def _candidate_snapshot(check: LiveCandidateCheck) -> dict:
    signal = check.candidate.signal
    return {
        "signal_id": signal.signal_id,
        "timestamp": signal.timestamp,
        "symbol": signal.symbol,
        "timeframe": signal.timeframe,
        "direction": signal.direction,
        "decision": check.decision,
        "reason": check.reason,
        "score": check.candidate.score,
        "tier": check.candidate.tier,
        "tradable": signal.tradable,
        "reject_reason": signal.reject_reason,
        "entry": check.entry,
        "stop": check.stop,
        "take_profit": check.take_profit,
        "age_minutes": check.age_minutes,
        "freshness_status": check.freshness_status,
        "risk_distance_pct": check.risk_distance_pct,
        "theoretical_max_position_size_usd": check.theoretical_max_position_usd,
        "capped_max_position_size_usd": check.capped_max_position_usd,
        "suggested_leverage": check.suggested_leverage,
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
    }


def _append_decision(record: dict, *, log_dir: Path) -> None:
    path = _decisions_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def _decisions_path(log_dir: Path) -> Path:
    return log_dir / DECISIONS_FILENAME


def _operator_ui_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Hammer Radar Approval Console</title>
  <style>
    :root { color-scheme: light; font-family: Arial, sans-serif; background: #f5f6f3; color: #202124; }
    body { margin: 0; }
    header { padding: 18px 24px; background: #18212f; color: white; }
    main { max-width: 1240px; margin: 0 auto; padding: 20px; }
    .banner { background: #fff7ed; border-bottom: 1px solid #fed7aa; color: #7c2d12; padding: 12px 24px; font-weight: 800; }
    .status, .controls, .readiness, .ticket, .exchange-dry-run, .live-safety, .live-connector, .binance-readonly, .binance-live-connector, .tiny-live-controls, .tiny-live-final-console, .tiny-live-actual-submit, .operator-actions, .strategy-performance, .strategy-promotion, .live-preflight, .notification-watcher, .alt-watchlist, .multi-symbol-scanner, .market-intelligence, .eth-paper-candidate, .eth-paper-outcome, .paper-refresh-scheduler, .betrayal-shadow, .paper-execution, .candidate, .decision, .feedback { background: white; border: 1px solid #d9ddd6; border-radius: 8px; padding: 14px; margin-bottom: 14px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 10px; }
    .controls-grid { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; }
    .label { color: #5d675f; font-size: 12px; text-transform: uppercase; }
    .value { font-weight: 700; overflow-wrap: anywhere; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 13px; }
    .danger { color: #9f1d1d; font-weight: 700; }
    .safe { color: #12613a; font-weight: 700; }
    .badge { display: inline-block; border-radius: 999px; padding: 5px 9px; font-size: 12px; font-weight: 800; letter-spacing: 0; }
    .badge-eligible { background: #dcfce7; border: 1px solid #86efac; color: #14532d; }
    .badge-paper { background: #fef3c7; border: 1px solid #fcd34d; color: #78350f; }
    .badge-forbidden { background: #fee2e2; border: 1px solid #fca5a5; color: #7f1d1d; }
    .candidate { border-left: 6px solid #9ca3af; }
    .candidate-eligible { border-left-color: #16a34a; }
    .candidate-paper { border-left-color: #d97706; }
    .candidate-forbidden { border-left-color: #dc2626; }
    .button-row { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
    button { padding: 8px 10px; border: 1px solid #aeb7ad; border-radius: 6px; background: #f2f5ef; cursor: pointer; font-weight: 700; }
    button:hover { background: #e6ece2; }
    button:disabled { color: #7a8178; background: #ecefeb; cursor: not-allowed; }
    .approve { background: #e9f8ee; border-color: #86efac; color: #14532d; }
    .reject { background: #fff1f2; border-color: #fecdd3; color: #7f1d1d; }
    input[type="text"], input[type="number"] { min-width: 180px; padding: 8px; border: 1px solid #b8c0b6; border-radius: 6px; }
    input.notes { width: min(560px, 100%); }
    pre { white-space: pre-wrap; background: #111827; color: #f9fafb; padding: 12px; border-radius: 6px; }
    .success { border-color: #86efac; background: #f0fdf4; color: #14532d; }
    .error { border-color: #fca5a5; background: #fef2f2; color: #7f1d1d; }
    .ready { border-left: 6px solid #16a34a; }
    .not-ready { border-left: 6px solid #dc2626; }
    .proposed { border-left: 6px solid #16a34a; }
    .blocked { border-left: 6px solid #dc2626; }
    .expired { border-left: 6px solid #d97706; }
    .muted { color: #667085; }
    h2 { margin-top: 28px; }
  </style>
</head>
<body>
  <header>
    <h1>Hammer Radar Approval Console</h1>
    <div>Record Decision only. No order placement. live_execution_enabled=false. order_placed=false.</div>
  </header>
  <div class="banner">
    LOCAL PAPER/MANUAL INTENT ONLY | No live order placement. | live_execution_enabled=false | order_placed=false
  </div>
  <main>
    <section class="status">
      <div class="grid">
        <div><div class="label">Health</div><div id="health" class="value">loading</div></div>
        <div><div class="label">live_execution_enabled</div><div id="live" class="value danger">false</div></div>
        <div><div class="label">order_placed</div><div id="order" class="value danger">false</div></div>
        <div><div class="label">Archive</div><div id="archive" class="value">loading</div></div>
        <div><div class="label">Generated</div><div id="generated" class="value">loading</div></div>
      </div>
    </section>

    <h2>Tiny Live Controls</h2>
    <section id="tinyLiveControls" class="tiny-live-controls blocked">
      <div class="grid">
        <div><div class="label">official lane</div><div id="tlcLane" class="value mono">BTCUSDT|8m|short|ladder_close_50_618</div></div>
        <div><div class="label">fresh cycle valid</div><div id="tlcFresh" class="value">loading</div></div>
        <div><div class="label">risk contract valid</div><div id="tlcRisk" class="value">loading</div></div>
        <div><div class="label">live execution enabled</div><div id="tlcLive" class="value danger">false</div></div>
        <div><div class="label">official lane allowed</div><div id="tlcLaneAllowed" class="value">loading</div></div>
        <div><div class="label">kill switch allows tiny-live</div><div id="tlcKill" class="value">loading</div></div>
        <div><div class="label">next required step</div><div id="tlcNext" class="value">loading</div></div>
        <div><div class="label">submit forbidden</div><div id="tlcForbidden" class="value danger">true</div></div>
      </div>
      <p><strong>Current blockers:</strong> <span id="tlcBlockers">loading</span></p>
      <p><strong>Risk contract reasons:</strong> <span id="tlcRiskReasons">loading</span></p>
      <p><strong>Risk contract root cause:</strong> <span id="tlcRiskRootCause">loading</span></p>
      <p><strong>Risk contract fix status:</strong> <span id="tlcRiskFixStatus">loading</span></p>
      <p class="muted">submit forbidden from this screen.</p>
      <div class="button-row">
        <input id="tlcReviewPhrase" class="notes" type="text" placeholder="Review confirmation phrase">
        <button onclick="recordTinyLiveControlsReview()">Record Controls Review</button>
      </div>
      <div class="button-row">
        <input id="tlcArmPhrase" class="notes" type="text" placeholder="Arming confirmation phrase">
        <input id="tlcArmReason" class="notes" type="text" placeholder="Reason">
        <button onclick="armTinyLiveControls()">Arm Controls Only</button>
      </div>
      <pre id="tlcRaw">loading</pre>
    </section>

    <h2>Tiny Live Final Console</h2>
    <section id="tinyLiveFinalConsole" class="tiny-live-final-console blocked">
      <div class="grid">
        <div><div class="label">official lane</div><div id="tlfLane" class="value mono">BTCUSDT|8m|short|ladder_close_50_618</div></div>
        <div><div class="label">overall status</div><div id="tlfOverall" class="value">loading</div></div>
        <div><div class="label">R262B valid</div><div id="tlfR262b" class="value">loading</div></div>
        <div><div class="label">signed triplet</div><div id="tlfTriplet" class="value">loading</div></div>
        <div><div class="label">controls armed</div><div id="tlfControls" class="value">loading</div></div>
        <div><div class="label">lane status</div><div id="tlfLaneStatus" class="value">loading</div></div>
        <div><div class="label">promotion status</div><div id="tlfPromotionStatus" class="value">loading</div></div>
        <div><div class="label">readiness</div><div id="tlfReadiness" class="value">loading</div></div>
        <div><div class="label">R264 checkpoint</div><div id="tlfR264" class="value">loading</div></div>
        <div><div class="label">submit forbidden</div><div id="tlfForbidden" class="value danger">true</div></div>
        <div><div class="label">exchange minimum reason</div><div id="tlfExchangeReason" class="value danger">loading</div></div>
        <div><div class="label">exchange min notional</div><div id="tlfExchangeMinNotional" class="value">loading</div></div>
        <div><div class="label">configured cap</div><div id="tlfConfiguredCap" class="value">loading</div></div>
        <div><div class="label">recommended decision</div><div id="tlfExchangeDecision" class="value">loading</div></div>
      </div>
      <p><strong>NO SUBMIT FROM THIS SCREEN.</strong> R263 can record review or arm controls only after exact experimental-lane acceptance.</p>
      <p><strong>Exchange-minimum decision:</strong> <span id="tlfExchangeSummary">loading</span></p>
      <p><strong>Safe next command:</strong> <span id="tlfExchangeCommand" class="mono">loading</span></p>
      <p><strong>Promoted lanes:</strong> <span id="tlfPromoted">loading</span></p>
      <p><strong>Readiness blockers:</strong> <span id="tlfBlockers">loading</span></p>
      <p><strong>Lane/Fisherman warning:</strong> <span id="tlfWarning">loading</span></p>
      <p><strong>Next required step:</strong> <span id="tlfNext">loading</span></p>
      <div class="button-row">
        <input id="tlfReviewPhrase" class="notes" type="text" placeholder="Final console review phrase">
        <button onclick="recordTinyLiveFinalConsoleReview()">Record Final Console Review</button>
      </div>
      <div class="button-row">
        <input id="tlfArmPhrase" class="notes" type="text" placeholder="R263 experimental-lane arming phrase">
        <input id="tlfArmReason" class="notes" type="text" placeholder="Reason">
        <button onclick="armTinyLiveFinalConsoleControls()">Arm From Final Console Only</button>
      </div>
      <pre id="tlfRaw">loading</pre>
    </section>

    <h2>Tiny Live Actual Submit Checkpoint</h2>
    <section id="tinyLiveActualSubmit" class="tiny-live-actual-submit blocked">
      <div class="grid">
        <div><div class="label">official lane</div><div id="tlaLane" class="value mono">BTCUSDT|8m|short|ladder_close_50_618</div></div>
        <div><div class="label">overall status</div><div id="tlaOverall" class="value">loading</div></div>
        <div><div class="label">pre-submit valid</div><div id="tlaValid" class="value">loading</div></div>
        <div><div class="label">R263 armed</div><div id="tlaArmed" class="value">loading</div></div>
        <div><div class="label">triplet fresh</div><div id="tlaFresh" class="value">loading</div></div>
        <div><div class="label">idempotency clean</div><div id="tlaIdem" class="value">loading</div></div>
        <div><div class="label">executed</div><div id="tlaExecuted" class="value danger">false</div></div>
        <div><div class="label">reconciled</div><div id="tlaReconciled" class="value">loading</div></div>
      </div>
      <p><strong>WARNING:</strong> no auto-submit. Execute requires the exact R264 phrase and explicit endpoint allow flag.</p>
      <p><strong>Blocked by:</strong> <span id="tlaBlockers">loading</span></p>
      <p><strong>Triplet:</strong> <span id="tlaTriplet">loading</span></p>
      <p><strong>Idempotency:</strong> <span id="tlaIdempotency">loading</span></p>
      <p><strong>Reconciliation:</strong> <span id="tlaReconciliation">loading</span></p>
      <p><strong>Partial success recovery:</strong> <span id="tlaRecovery">loading</span></p>
      <p><strong>Exact live command:</strong></p>
      <pre id="tlaCommand">loading</pre>
      <div class="button-row">
        <input id="tlaDryPhrase" class="notes" type="text" placeholder="R264 dry preview phrase">
        <button onclick="recordTinyLiveActualSubmitDryPreview()">Record Dry Preview Only</button>
      </div>
      <div class="button-row">
        <input id="tlaLivePhrase" class="notes" type="text" placeholder="R264 exact live submit phrase">
        <input id="tlaLiveReason" class="notes" type="text" placeholder="Reason">
        <label><input id="tlaAllowEndpoint" type="checkbox"> allow Binance order endpoint</label>
        <button class="reject" onclick="executeTinyLiveActualSubmit()">Execute Exact Live Submit</button>
      </div>
      <pre id="tlaRaw">loading</pre>
    </section>

    <h2>Tiny Live JIT Launch Packet</h2>
    <section id="tinyLiveJitLaunchPacket" class="tiny-live-jit-launch blocked">
      <div class="grid">
        <div><div class="label">official lane</div><div id="tljLane" class="value mono">BTCUSDT|8m|short|ladder_close_50_618</div></div>
        <div><div class="label">overall status</div><div id="tljOverall" class="value">loading</div></div>
        <div><div class="label">R262B fresh</div><div id="tljR262b" class="value">loading</div></div>
        <div><div class="label">R263 armed</div><div id="tljR263" class="value">loading</div></div>
        <div><div class="label">R264 dry preview</div><div id="tljR264" class="value">loading</div></div>
        <div><div class="label">idempotency clean</div><div id="tljIdem" class="value">loading</div></div>
        <div><div class="label">manual command</div><div id="tljCommandAvailable" class="value">loading</div></div>
        <div><div class="label">submit allowed</div><div id="tljSubmitAllowed" class="value danger">false</div></div>
        <div><div class="label">order placed</div><div id="tljOrderPlaced" class="value danger">false</div></div>
        <div><div class="label">recorded</div><div id="tljRecorded" class="value">false</div></div>
      </div>
      <p><strong>GIANT WARNING:</strong> no submit from this screen. This card prepares and records only the JIT packet.</p>
      <p><strong>Experimental lane:</strong> <span id="tljWarning">8m short is paper-only/promotion-mismatched; exact R263 acceptance is required.</span></p>
      <p><strong>Blocked by:</strong> <span id="tljBlockers">loading</span></p>
      <p><strong>Next required step:</strong> <span id="tljNext">loading</span></p>
      <p><strong>Recommended operator move:</strong> <span id="tljOperatorMove">loading</span></p>
      <p><strong>Manual live command packet:</strong></p>
      <pre id="tljCommand">loading</pre>
      <div class="button-row">
        <input id="tljPhrase" class="notes" type="text" placeholder="R264B JIT prep confirmation phrase">
        <input id="tljReason" class="notes" type="text" placeholder="Reason">
        <label><input id="tljRecord" type="checkbox" checked> record JIT packet</label>
        <button onclick="runTinyLiveJitLaunchPrep()">Run JIT Prep Only</button>
      </div>
      <pre id="tljRaw">loading</pre>
    </section>

    <h2>Friday Readiness</h2>
    <section id="readiness" class="readiness not-ready">
      <div class="grid">
        <div><div class="label">readiness_status</div><div id="readyStatus" class="value danger">loading</div></div>
        <div><div class="label">allowed_now</div><div id="allowedNow" class="value danger">false</div></div>
        <div><div class="label">fresh eligible count</div><div id="freshEligible" class="value">loading</div></div>
        <div><div class="label">manual outcomes today</div><div id="outcomesToday" class="value">loading</div></div>
        <div><div class="label">losses today</div><div id="lossesToday" class="value">loading</div></div>
        <div><div class="label">pnl today</div><div id="pnlToday" class="value">loading</div></div>
        <div><div class="label">live_execution_enabled</div><div id="readinessLive" class="value danger">false</div></div>
        <div><div class="label">order_placed</div><div id="readinessOrder" class="value danger">false</div></div>
      </div>
      <p><strong>Protocol:</strong> R267 BTCUSDT tiny live uses 80 USDT max notional, visible 10x leverage, about 8 USDT derived margin, isolated margin, max 1 manual tiny-live trade per day, stop after 1 loss or -5 USDT.</p>
      <p id="readinessReason">loading</p>
      <p><strong>Blockers:</strong> <span id="readinessBlockers">loading</span></p>
      <p><strong>Next required action:</strong> <span id="nextAction">loading</span></p>
      <p class="muted">If NOT_READY, manual live trade should not be taken now. If READY: Log decision before manual exchange action. App does not place orders.</p>
    </section>

    <h2>Machine Trade Ticket</h2>
    <section id="tradeTicket" class="ticket blocked">
      <div class="grid">
        <div><div class="label">ticket_status</div><div id="ticketStatus" class="value danger">loading</div></div>
        <div><div class="label">readiness_status</div><div id="ticketReadiness" class="value danger">loading</div></div>
        <div><div class="label">allowed_now</div><div id="ticketAllowed" class="value danger">false</div></div>
        <div><div class="label">signal_id</div><div id="ticketSignal" class="value mono">loading</div></div>
        <div><div class="label">direction/timeframe</div><div id="ticketDirection" class="value">loading</div></div>
        <div><div class="label">entry</div><div id="ticketEntry" class="value">loading</div></div>
        <div><div class="label">stop</div><div id="ticketStop" class="value">loading</div></div>
        <div><div class="label">take_profit</div><div id="ticketTakeProfit" class="value">loading</div></div>
        <div><div class="label">suggested_position_usd</div><div id="ticketPosition" class="value">loading</div></div>
        <div><div class="label">suggested_leverage</div><div id="ticketLeverage" class="value">loading</div></div>
        <div><div class="label">max_loss_usd</div><div id="ticketMaxLoss" class="value">loading</div></div>
        <div><div class="label">margin_mode</div><div id="ticketMargin" class="value">isolated</div></div>
        <div><div class="label">live_execution_enabled</div><div id="ticketLive" class="value danger">false</div></div>
        <div><div class="label">order_placed</div><div id="ticketOrder" class="value danger">false</div></div>
      </div>
      <p><strong>Blockers:</strong> <span id="ticketBlockers">loading</span></p>
      <p><strong>Machine reason:</strong> <span id="ticketReason">loading</span></p>
      <p class="muted">No order will be placed. This records approval intent only.</p>
      <p class="muted">Paper execution only. No live order will be placed.</p>
      <p id="paperExecutionBlocked" class="muted">Blocked: no paper execution without PROPOSED ticket.</p>
      <p><input id="ticketNotes" class="notes" placeholder="paper ticket approval notes"></p>
      <div class="button-row">
        <button class="approve" id="approveTicketButton" onclick="approvePaperTicket()" disabled>Approve Paper Ticket</button>
        <button class="approve" id="executePaperButton" onclick="executePaperTicket()" disabled>Execute Paper Ticket</button>
        <button class="reject" onclick="recordTicketWatch()">Reject / Watch</button>
      </div>
    </section>

    <h2>Exchange Dry Run</h2>
    <section id="exchangeDryRun" class="exchange-dry-run blocked">
      <div class="grid">
        <div><div class="label">validation_status</div><div id="dryRunStatus" class="value danger">loading</div></div>
        <div><div class="label">exchange</div><div id="dryRunExchange" class="value">loading</div></div>
        <div><div class="label">symbol</div><div id="dryRunSymbol" class="value">loading</div></div>
        <div><div class="label">side</div><div id="dryRunSide" class="value">loading</div></div>
        <div><div class="label">position_side</div><div id="dryRunPositionSide" class="value">loading</div></div>
        <div><div class="label">notional_usd</div><div id="dryRunNotional" class="value">loading</div></div>
        <div><div class="label">quantity_rounded</div><div id="dryRunQuantity" class="value">loading</div></div>
        <div><div class="label">entry_price_rounded</div><div id="dryRunEntry" class="value">loading</div></div>
        <div><div class="label">stop_price_rounded</div><div id="dryRunStop" class="value">loading</div></div>
        <div><div class="label">take_profit_price_rounded</div><div id="dryRunTakeProfit" class="value">loading</div></div>
        <div><div class="label">leverage</div><div id="dryRunLeverage" class="value">loading</div></div>
        <div><div class="label">margin_mode</div><div id="dryRunMargin" class="value">loading</div></div>
        <div><div class="label">live_execution_enabled</div><div id="dryRunLive" class="value danger">false</div></div>
        <div><div class="label">order_placed</div><div id="dryRunOrder" class="value danger">false</div></div>
        <div><div class="label">dry_run</div><div id="dryRunFlag" class="value safe">true</div></div>
      </div>
      <p><strong>Blockers:</strong> <span id="dryRunBlockers">loading</span></p>
      <p class="muted">Exchange dry run only. No order was sent. No API key used. No Binance order placement exists.</p>
    </section>

    <h2>Live Safety Envelope</h2>
    <section id="liveSafety" class="live-safety blocked">
      <div class="grid">
        <div><div class="label">live_safety_status</div><div id="liveSafetyStatus" class="value danger">loading</div></div>
        <div><div class="label">live_execution_enabled</div><div id="liveSafetyEnabled" class="value danger">false</div></div>
        <div><div class="label">order_placed</div><div id="liveSafetyOrder" class="value danger">false</div></div>
        <div><div class="label">kill_switch_active</div><div id="liveSafetyKill" class="value danger">true</div></div>
        <div><div class="label">allow_live_orders</div><div id="liveSafetyAllow" class="value danger">false</div></div>
      </div>
      <p><strong>Blockers:</strong> <span id="liveSafetyBlockers">loading</span></p>
      <p><strong>Failed gates:</strong> <span id="liveSafetyFailed">loading</span></p>
      <p><strong>Passed gates:</strong> <span id="liveSafetyPassed">loading</span></p>
      <p><strong>Next required action:</strong> <span id="liveSafetyNext">loading</span></p>
      <p><strong>Protocol:</strong> <span id="liveSafetyProtocol">R267 BTCUSDT 80 USDT max notional, 10x visible leverage, about 8 USDT derived margin, isolated margin, 1 trade/day, stop after -5 USDT or 1 loss.</span></p>
      <p class="muted">Live execution is disabled. Kill switch is active by default. No live order can be placed from this system in the current mode. This panel is a safety pre-check only.</p>
    </section>

    <h2>Live Connector Stub</h2>
    <section id="liveConnectorStub" class="live-connector blocked">
      <div class="grid">
        <div><div class="label">connector_mode</div><div id="connectorMode" class="value danger">stub_no_order</div></div>
        <div><div class="label">live_execution_enabled</div><div id="connectorLive" class="value danger">false</div></div>
        <div><div class="label">order_placed</div><div id="connectorOrder" class="value danger">false</div></div>
        <div><div class="label">safety status</div><div id="connectorSafety" class="value danger">loading</div></div>
        <div><div class="label">kill switch active</div><div id="connectorKill" class="value danger">true</div></div>
      </div>
      <p><strong>Last live attempt:</strong> <span id="lastLiveAttempt">loading</span></p>
      <p class="muted">No real order can be placed. Stub connector only records rejected attempts. No API key is used. No Binance/network call exists.</p>
      <div class="button-row">
        <button class="reject" id="stubSubmitButton" onclick="submitLiveConnectorStub()" disabled>Test Live Connector Stub</button>
        <span class="muted">Records rejected no-order attempt</span>
      </div>
    </section>

    <h2>Binance Read-Only Connector</h2>
    <section id="binanceReadonly" class="binance-readonly blocked">
      <div class="grid">
        <div><div class="label">connector_status</div><div id="binanceStatus" class="value danger">loading</div></div>
        <div><div class="label">connector_mode</div><div id="binanceMode" class="value">loading</div></div>
        <div><div class="label">api_key_present</div><div id="binanceApiKeyPresent" class="value">false</div></div>
        <div><div class="label">api_secret_present</div><div id="binanceApiSecretPresent" class="value">false</div></div>
        <div><div class="label">api_key_preview</div><div id="binanceApiKeyPreview" class="value mono">n/a</div></div>
        <div><div class="label">live_trading_env</div><div id="binanceLiveTradingEnv" class="value danger">loading</div></div>
        <div><div class="label">live_execution_enabled</div><div id="binanceLive" class="value danger">false</div></div>
        <div><div class="label">order_placed</div><div id="binanceOrder" class="value danger">false</div></div>
      </div>
      <p><strong>Blockers:</strong> <span id="binanceBlockers">loading</span></p>
      <p><strong>Forbidden actions:</strong> <span id="binanceForbidden">loading</span></p>
      <p class="muted">Read-only connector. No order placement exists.</p>
      <p class="muted">Secrets are never shown. Live trading env must remain false.</p>
    </section>

    <h2>Binance Live Connector</h2>
    <section id="binanceLiveConnector" class="binance-live-connector blocked">
      <div class="grid">
        <div><div class="label">connector_mode</div><div id="binanceLiveConnectorMode" class="value danger">DRY_RUN_ONLY</div></div>
        <div><div class="label">readiness</div><div id="binanceLiveConnectorReadiness" class="value danger">BLOCKED</div></div>
        <div><div class="label">api_key_present</div><div id="binanceLiveConnectorKey" class="value">false</div></div>
        <div><div class="label">api_secret_present</div><div id="binanceLiveConnectorSecret" class="value">false</div></div>
        <div><div class="label">test_order_network_enabled</div><div id="binanceLiveConnectorTestNetwork" class="value danger">false</div></div>
        <div><div class="label">signing_available</div><div id="binanceLiveConnectorSigning" class="value">false</div></div>
        <div><div class="label">live_order_adapter_configured</div><div id="binanceLiveConnectorAdapter" class="value danger">false</div></div>
        <div><div class="label">protective_orders_supported</div><div id="binanceLiveConnectorProtective" class="value danger">false</div></div>
        <div><div class="label">protective_orders_required</div><div id="binanceLiveConnectorProtectiveRequired" class="value danger">true</div></div>
        <div><div class="label">protective_orders_ready</div><div id="binanceLiveConnectorProtectiveReady" class="value danger">false</div></div>
        <div><div class="label">protective_order_mode</div><div id="binanceLiveConnectorProtectiveMode" class="value danger">PREVIEW_ONLY</div></div>
        <div><div class="label">protective stop/take-profit</div><div id="binanceLiveConnectorProtectiveTypes" class="value mono">STOP_MARKET / TAKE_PROFIT_MARKET</div></div>
        <div><div class="label">real_live_endpoint_prepared</div><div id="binanceLiveConnectorRealEndpoint" class="value">false</div></div>
        <div><div class="label">live_execution_enabled</div><div id="binanceLiveConnectorLive" class="value danger">false</div></div>
        <div><div class="label">allow_live_orders</div><div id="binanceLiveConnectorAllow" class="value danger">false</div></div>
        <div><div class="label">global_kill_switch</div><div id="binanceLiveConnectorKill" class="value danger">true</div></div>
        <div><div class="label">latest attempt</div><div id="binanceLiveConnectorLatest" class="value mono">loading</div></div>
        <div><div class="label">payload preview status</div><div id="binanceLiveConnectorPreview" class="value danger">loading</div></div>
      </div>
      <p><strong>Blockers:</strong> <span id="binanceLiveConnectorBlockers">loading</span></p>
      <p class="muted">No random altcoins.</p>
      <p class="muted">No vague live commands.</p>
      <p class="muted">Exact LIVE APPROVE &lt;signal_id&gt; required.</p>
      <p class="muted">Payload preview is not permission to execute. Test-order mode is not live order placement.</p>
      <p class="muted">Test order only. No matching-engine submission.</p>
      <p class="muted">No real orders.</p>
      <p class="muted">Secrets and signatures are hidden.</p>
      <p class="muted">Default blocked.</p>
      <p class="muted">No naked live entries.</p>
      <p class="muted">Protective stop and take-profit required.</p>
      <p class="muted">Secrets/signatures hidden.</p>
      <p class="muted">No random altcoins / no shorts / no vague commands.</p>
    </section>

    <h2>First Live Runbook</h2>
    <section id="firstLiveRunbook" class="operator-actions blocked">
      <div class="grid">
        <div><div class="label">runbook_status</div><div id="firstLiveRunbookStatus" class="value danger">loading</div></div>
        <div><div class="label">gate_decision</div><div id="firstLiveGateDecision" class="value danger">NO_GO</div></div>
        <div><div class="label">signal_id</div><div id="firstLiveSignalId" class="value mono">none</div></div>
        <div><div class="label">checklist</div><div id="firstLiveChecklist" class="value">loading</div></div>
      </div>
      <p><strong>Blockers:</strong> <span id="firstLiveBlockers">loading</span></p>
      <p><strong>Enablement plan:</strong> <span id="firstLivePlan">none</span></p>
      <p class="muted">Runbook only.</p>
      <p class="muted">Does not flip env.</p>
      <p class="muted">Does not place orders.</p>
      <p class="muted">Lock back down after one attempt.</p>
      <p class="muted">Exact LIVE APPROVE &lt;signal_id&gt; required.</p>
      <p class="muted">Protective stop-loss and take-profit required.</p>
      <p class="muted">Test-order validation required.</p>
    </section>

    <h2>Operator Actions / Binance Live Readiness</h2>
    <section id="operatorActions" class="operator-actions blocked">
      <div class="grid">
        <div><div class="label">operator actions</div><div class="value danger">record-only</div></div>
        <div><div class="label">live orders</div><div class="value danger">disabled</div></div>
        <div><div class="label">live readiness symbol</div><div class="value safe">BTCUSDT</div></div>
        <div><div class="label">ETH / alts</div><div class="value">paper/watch-only</div></div>
      </div>
      <p class="muted">Operator actions are record-only.</p>
      <p class="muted">No live orders.</p>
      <p class="muted">Live API credentials may be present, but live execution remains disabled.</p>
      <p class="muted">BTCUSDT remains the only live-readiness symbol.</p>
      <p class="muted">ETH/alts remain paper/watch-only.</p>
      <p class="muted">Exact live approval requires signal_id.</p>
      <p class="muted">R39 evaluates only; no live orders.</p>
      <p class="muted">Execution remains disabled.</p>
    </section>

    <h2>Strategy Performance</h2>
    <section id="strategyPerformance" class="strategy-performance blocked">
      <div class="grid">
        <div><div class="label">audit mode</div><div class="value danger">Audit only.</div></div>
        <div><div class="label">live orders</div><div class="value danger">No live orders.</div></div>
        <div><div class="label">execution_enabled</div><div id="strategyExecution" class="value danger">false</div></div>
        <div><div class="label">order_placed</div><div id="strategyOrder" class="value danger">false</div></div>
        <div><div class="label">no_order_payload_created</div><div id="strategyPayload" class="value safe">true</div></div>
        <div><div class="label">eligible recommendations</div><div id="strategyEligibleCount" class="value">loading</div></div>
      </div>
      <p class="muted">Eligibility is recommendation, not permission.</p>
      <p class="muted">Future tiny-live still requires exact LIVE APPROVE signal_id and all safety gates.</p>
      <p><strong>Top recommendation:</strong> <span id="strategyTopRecommendation">loading</span></p>
    </section>

    <h2>Strategy Promotion</h2>
    <section id="strategyPromotion" class="strategy-promotion blocked">
      <div class="grid">
        <div><div class="label">mode</div><div class="value danger">Promotion is review only.</div></div>
        <div><div class="label">live orders</div><div class="value danger">No live orders.</div></div>
        <div><div class="label">execution</div><div class="value danger">Execution remains disabled.</div></div>
        <div><div class="label">near promotion</div><div id="promotionNearCount" class="value">loading</div></div>
        <div><div class="label">eligible buckets</div><div id="promotionReadyCount" class="value">loading</div></div>
        <div><div class="label">latest event</div><div id="promotionLatest" class="value mono">loading</div></div>
      </div>
      <p><strong>Top near-promotion:</strong> <span id="promotionNearTop">loading</span></p>
      <p><strong>Top eligible:</strong> <span id="promotionReadyTop">loading</span></p>
    </section>

    <h2>Live Preflight</h2>
    <section id="livePreflight" class="live-preflight blocked">
      <div class="grid">
        <div><div class="label">mode</div><div class="value danger">Preflight only.</div></div>
        <div><div class="label">live orders</div><div class="value danger">No live orders.</div></div>
        <div><div class="label">approval command</div><div class="value danger">Exact LIVE APPROVE &lt;signal_id&gt; required later.</div></div>
        <div><div class="label">execution</div><div class="value danger">Execution remains disabled.</div></div>
        <div><div class="label">preflight_status</div><div id="preflightStatus" class="value danger">loading</div></div>
        <div><div class="label">promoted strategy ready</div><div id="preflightPromotedReady" class="value">loading</div></div>
        <div><div class="label">fresh matching signal</div><div id="preflightSignalFound" class="value">loading</div></div>
        <div><div class="label">latest pack</div><div id="preflightLatest" class="value mono">loading</div></div>
      </div>
      <p><strong>Strategy:</strong> <span id="preflightStrategy">loading</span></p>
      <p><strong>Candidate signal:</strong> <span id="preflightSignal" class="mono">loading</span></p>
      <p><strong>Next action:</strong> <span id="preflightNextAction">loading</span></p>
      <p class="muted">Recommendation/preflight only, not permission to execute.</p>
      <p class="muted">No signed payloads.</p>
    </section>

    <h2>Notification Watcher</h2>
    <section id="notificationWatcher" class="notification-watcher blocked">
      <div class="grid">
        <div><div class="label">telegram_enabled</div><div id="notificationTelegramEnabled" class="value">loading</div></div>
        <div><div class="label">telegram_configured</div><div id="notificationTelegramConfigured" class="value">loading</div></div>
        <div><div class="label">alerts_recorded</div><div id="notificationAlertsRecorded" class="value">loading</div></div>
        <div><div class="label">last alert</div><div id="notificationLastAlert" class="value">loading</div></div>
        <div><div class="label">live_execution_enabled</div><div id="notificationLive" class="value danger">false</div></div>
        <div><div class="label">order_placed</div><div id="notificationOrder" class="value danger">false</div></div>
      </div>
      <p class="muted">Alerts only. No order placement.</p>
      <p class="muted">Secrets are never shown.</p>
      <p class="muted">Use this so you do not need to watch the UI constantly.</p>
      <div class="button-row">
        <button onclick="checkNotifications(false, 'none')">Check Notifications</button>
        <button class="approve" onclick="checkNotifications(true, 'telegram')">Send Telegram Check</button>
      </div>
      <div id="notificationCheckResult" class="muted">No notification check yet.</div>
    </section>

    <h2>ETH / Alt Watchlist</h2>
    <section id="altWatchlist" class="alt-watchlist blocked">
      <div class="grid">
        <div><div class="label">btc_live_only</div><div id="watchlistBtcLiveOnly" class="value safe">true</div></div>
        <div><div class="label">total symbols</div><div id="watchlistTotalSymbols" class="value">loading</div></div>
        <div><div class="label">live eligible symbols</div><div id="watchlistLiveEligible" class="value">loading</div></div>
        <div><div class="label">paper watch symbols</div><div id="watchlistPaperSymbols" class="value">loading</div></div>
        <div><div class="label">relative strength symbols</div><div id="watchlistRelativeSymbols" class="value">loading</div></div>
        <div><div class="label">key rotation pair</div><div id="watchlistKeyPair" class="value">ETHBTC</div></div>
        <div><div class="label">next promotion candidate</div><div id="watchlistPromotion" class="value">ETHUSDT</div></div>
      </div>
      <p><strong>Warning:</strong> <span id="watchlistWarning">ETHUSDT, ETHBTC, and alts are paper/watch-only in R30</span></p>
      <p class="muted">BTCUSDT remains the only live-readiness symbol.</p>
      <p class="muted">ETHUSDT and ETHBTC are watchlist and paper-only.</p>
      <p class="muted">ETHBTC tracks ETH strength vs BTC / alt-cycle rotation.</p>
      <p class="muted">No alt live tickets.</p>
      <p class="muted">No alt live orders.</p>
      <div id="watchlistSymbols" class="muted">loading</div>
    </section>

    <h2>Multi-Symbol Paper Scanner</h2>
    <section id="multiSymbolScanner" class="multi-symbol-scanner blocked">
      <div class="grid">
        <div><div class="label">live_execution_enabled</div><div id="multiSymbolLive" class="value danger">false</div></div>
        <div><div class="label">order_placed</div><div id="multiSymbolOrder" class="value danger">false</div></div>
        <div><div class="label">btc_live_only</div><div id="multiSymbolBtcOnly" class="value safe">true</div></div>
        <div><div class="label">scanned symbols</div><div id="multiSymbolScanned" class="value">loading</div></div>
        <div><div class="label">archived scan records</div><div id="multiSymbolArchived" class="value">loading</div></div>
        <div><div class="label">key rotation pair</div><div id="multiSymbolKeyPair" class="value">ETHBTC</div></div>
        <div><div class="label">next promotion candidate</div><div id="multiSymbolPromotion" class="value">ETHUSDT</div></div>
      </div>
      <p class="muted">Paper/watch-only. No alt live tickets.</p>
      <p class="muted">BTCUSDT remains the only live-readiness symbol.</p>
      <p class="muted">ETHBTC is a rotation compass, not a live order target.</p>
      <div class="button-row">
        <button onclick="runMultiSymbolScan(false)">Preview Multi-Symbol Scan</button>
        <button onclick="runMultiSymbolScan(true)">Archive Multi-Symbol Scan</button>
      </div>
      <div id="multiSymbolTopRanked" class="muted">loading</div>
      <div id="multiSymbolScanResult" class="muted">No multi-symbol scan yet.</div>
    </section>

    <h2>Market Intelligence</h2>
    <section id="marketIntelligence" class="market-intelligence blocked">
      <div class="grid">
        <div><div class="label">live_execution_enabled</div><div id="marketIntelLive" class="value danger">false</div></div>
        <div><div class="label">order_placed</div><div id="marketIntelOrder" class="value danger">false</div></div>
        <div><div class="label">market_data_status</div><div id="marketIntelStatus" class="value">loading</div></div>
        <div><div class="label">network_used</div><div id="marketIntelNetwork" class="value">false</div></div>
        <div><div class="label">key rotation pair</div><div id="marketIntelKeyPair" class="value">ETHBTC</div></div>
        <div><div class="label">ETHBTC rotation state</div><div id="marketIntelRotationState" class="value">loading</div></div>
      </div>
      <p><strong>Warning:</strong> <span id="marketIntelWarning">market intelligence is public/read-only and paper/watch-only</span></p>
      <p class="muted">Public/read-only market data only.</p>
      <p class="muted">No live tickets for ETH/alts.</p>
      <p class="muted">BTCUSDT remains the only live-readiness symbol.</p>
      <div class="button-row">
        <button onclick="loadMarketIntelligence(false)">Refresh Market Intelligence</button>
        <button onclick="loadMarketIntelligence(true)">Archive Market Intelligence Snapshot</button>
      </div>
      <div id="marketIntelTopRanked" class="muted">loading</div>
      <div class="market-intelligence">
        <h3>ETHBTC Rotation</h3>
        <div class="grid">
          <div><div class="label">ETHBTC price</div><div id="ethbtcPrice" class="value">n/a</div></div>
          <div><div class="label">24h change</div><div id="ethbtcChange" class="value">n/a</div></div>
          <div><div class="label">rotation_state</div><div id="ethbtcRotationState" class="value">UNKNOWN</div></div>
          <div><div class="label">interpretation</div><div id="ethbtcInterpretation" class="value">loading</div></div>
        </div>
      </div>
    </section>

    <h2>ETHUSDT Paper Candidate Engine</h2>
    <section id="ethPaperCandidate" class="eth-paper-candidate blocked">
      <div class="grid">
        <div><div class="label">live_execution_enabled</div><div id="ethPaperLive" class="value danger">false</div></div>
        <div><div class="label">order_placed</div><div id="ethPaperOrder" class="value danger">false</div></div>
        <div><div class="label">symbol</div><div id="ethPaperSymbol" class="value mono">ETHUSDT</div></div>
        <div><div class="label">rotation pair</div><div id="ethPaperRotationPair" class="value mono">ETHBTC</div></div>
        <div><div class="label">rotation state</div><div id="ethPaperRotationState" class="value">loading</div></div>
        <div><div class="label">candidate tier/status</div><div id="ethPaperTierStatus" class="value">loading</div></div>
        <div><div class="label">direction</div><div id="ethPaperDirection" class="value">loading</div></div>
        <div><div class="label">score</div><div id="ethPaperScore" class="value">loading</div></div>
      </div>
      <p><strong>Reason:</strong> <span id="ethPaperReason">loading</span></p>
      <p><strong>Latest candidate:</strong> <span id="ethPaperLatest">loading</span></p>
      <p class="muted">ETHUSDT is paper-only.</p>
      <p class="muted">ETHBTC is rotation context only.</p>
      <p class="muted">BTCUSDT remains the only live-readiness symbol.</p>
      <p class="muted">No ETH live tickets. No ETH live orders.</p>
      <div class="button-row">
        <button onclick="loadEthPaperCandidate(false)">Preview ETH Paper Candidate</button>
        <button onclick="loadEthPaperCandidate(true)">Archive ETH Paper Candidate</button>
      </div>
    </section>

    <h2>ETHUSDT Paper Outcome Tracker</h2>
    <section id="ethPaperOutcome" class="eth-paper-outcome blocked">
      <div class="grid">
        <div><div class="label">live_execution_enabled</div><div id="ethOutcomeLive" class="value danger">false</div></div>
        <div><div class="label">order_placed</div><div id="ethOutcomeOrder" class="value danger">false</div></div>
        <div><div class="label">symbol</div><div id="ethOutcomeSymbol" class="value mono">ETHUSDT</div></div>
        <div><div class="label">rotation pair</div><div id="ethOutcomeRotationPair" class="value mono">ETHBTC</div></div>
        <div><div class="label">total outcomes</div><div id="ethOutcomeTotal" class="value">loading</div></div>
        <div><div class="label">wins</div><div id="ethOutcomeWins" class="value">loading</div></div>
        <div><div class="label">losses</div><div id="ethOutcomeLosses" class="value">loading</div></div>
        <div><div class="label">open</div><div id="ethOutcomeOpen" class="value">loading</div></div>
        <div><div class="label">unresolved</div><div id="ethOutcomeUnresolved" class="value">loading</div></div>
        <div><div class="label">no-data</div><div id="ethOutcomeNoData" class="value">loading</div></div>
        <div><div class="label">rotation state</div><div id="ethOutcomeRotationState" class="value">UNKNOWN</div></div>
      </div>
      <p><strong>Latest outcome:</strong> <span id="ethOutcomeLatest">loading</span></p>
      <p class="muted">ETHUSDT outcomes are paper-only.</p>
      <p class="muted">No ETH live tickets.</p>
      <p class="muted">No ETH live orders.</p>
      <p class="muted">BTCUSDT remains the only live-readiness symbol.</p>
      <div class="button-row">
        <button onclick="loadEthPaperOutcome(false)">Preview ETH Paper Outcome</button>
        <button onclick="loadEthPaperOutcome(true)">Archive ETH Paper Outcome</button>
      </div>
    </section>

    <h2>Paper Refresh Scheduler</h2>
    <section id="paperRefreshScheduler" class="paper-refresh-scheduler blocked">
      <div class="grid">
        <div><div class="label">live_execution_enabled</div><div id="paperRefreshLive" class="value danger">false</div></div>
        <div><div class="label">order_placed</div><div id="paperRefreshOrder" class="value danger">false</div></div>
        <div><div class="label">btc_live_only</div><div id="paperRefreshBtcOnly" class="value safe">true</div></div>
        <div><div class="label">available tasks</div><div id="paperRefreshTasks" class="value">loading</div></div>
        <div><div class="label">runs recorded</div><div id="paperRefreshRuns" class="value">loading</div></div>
        <div><div class="label">last run</div><div id="paperRefreshLastRun" class="value">loading</div></div>
        <div><div class="label">configured poll seconds</div><div id="paperRefreshPoll" class="value">loading</div></div>
        <div><div class="label">systemd service</div><div id="paperRefreshService" class="value mono">hammer-paper-refresh.service</div></div>
        <div><div class="label">watcher entrypoint</div><div id="paperRefreshEntrypoint" class="value mono">loading</div></div>
      </div>
      <p class="muted">Paper/watch refresh only.</p>
      <p class="muted">No live orders.</p>
      <p class="muted">No ETH/alt live tickets.</p>
      <p class="muted">BTCUSDT remains the only live-readiness symbol.</p>
      <p class="muted">Systemd service available: hammer-paper-refresh.service</p>
      <p class="muted">Use status/log commands before enabling.</p>
      <div class="button-row">
        <button onclick="runPaperRefresh(false)">Run Paper Refresh</button>
        <button onclick="runPaperRefresh(true)">Run Paper Refresh + Notify If Ready</button>
      </div>
    </section>

    <h2>Betrayal Shadow Outcomes</h2>
    <section id="betrayalShadow" class="betrayal-shadow blocked">
      <div class="grid">
        <div><div class="label">shadow_only</div><div id="betrayalShadowOnly" class="value safe">true</div></div>
        <div><div class="label">live_execution_enabled</div><div id="betrayalShadowLive" class="value danger">false</div></div>
        <div><div class="label">order_placed</div><div id="betrayalShadowOrder" class="value danger">false</div></div>
        <div><div class="label">total records</div><div id="betrayalShadowTotal" class="value">loading</div></div>
        <div><div class="label">wins</div><div id="betrayalShadowWins" class="value">loading</div></div>
        <div><div class="label">losses</div><div id="betrayalShadowLosses" class="value">loading</div></div>
        <div><div class="label">unresolved/no-data</div><div id="betrayalShadowUnknown" class="value">loading</div></div>
        <div><div class="label">win rate</div><div id="betrayalShadowWinRate" class="value">n/a</div></div>
        <div><div class="label">avg shadow pnl</div><div id="betrayalShadowAvgPnl" class="value">n/a</div></div>
      </div>
      <p class="muted">Betrayal remains shadow-only. No live order can be placed. This does not affect Friday readiness. This does not affect trade tickets.</p>
      <div class="button-row">
        <button onclick="trackBetrayalShadows()">Track Betrayal Shadows</button>
        <span class="muted">Shadow tracking only. does not affect readiness or live trading.</span>
      </div>
      <div id="betrayalShadowRecords" class="muted">loading</div>
    </section>

    <h2>Paper Executions</h2>
    <div id="paperExecutions">loading</div>

    <section class="controls">
      <div class="controls-grid">
        <label><input id="latestOnly" type="checkbox" checked> Latest only</label>
        <label><input id="eligibleOnly" type="checkbox"> Eligible only</label>
        <label><input id="includeForbidden" type="checkbox" checked> Include forbidden</label>
        <label><input id="allowShort" type="checkbox"> Allow short</label>
        <label>Limit <input id="limit" type="number" min="1" max="100" value="10"></label>
        <label>Operator <input id="operator" type="text" value="josue"></label>
        <button onclick="refreshAll()">Refresh</button>
      </div>
    </section>

    <h2>Candidates</h2>
    <div id="candidates">loading</div>

    <h2>Recent Decisions</h2>
    <div id="decisions">loading</div>

    <h2>Last Action</h2>
    <section id="message" class="feedback">No action yet. order_placed=false.</section>
  </main>
<script>
let currentCandidates = [];
let currentTicket = null;

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function setBool(id, value) {
  const node = document.getElementById(id);
  node.textContent = String(Boolean(value));
  node.className = "value " + (value ? "safe" : "danger");
}

async function refreshAll() {
  await loadHealth();
  await loadTinyLiveControls();
  await loadTinyLiveFinalConsole();
  await loadTinyLiveActualSubmit();
  await loadTinyLiveJitLaunchPacket();
  await loadReadiness();
  await loadTradeTicket();
  await loadExchangeDryRun();
  await loadLiveSafety();
  await loadLiveAttempts();
  await loadBinanceReadonlyStatus();
  await loadBinanceLiveConnector();
  await loadStrategyPerformance();
  await loadStrategyPromotion();
  await loadLivePreflight();
  await loadFirstLiveRunbook();
  await loadNotificationStatus();
  await loadAltWatchlist();
  await loadMultiSymbolSummary();
  await loadMarketIntelligence(false);
  await loadEthPaperSummary();
  await loadEthPaperOutcomeSummary();
  await loadPaperRefreshStatus();
  await loadBetrayalShadowOutcomes();
  await loadPaperExecutions();
  await loadCandidates();
  await loadDecisions();
}

async function loadTinyLiveControls() {
  const res = await fetch('/tiny-live/controls/review');
  const data = await res.json();
  const riskRes = await fetch('/tiny-live/risk-contract/review');
  const riskData = await riskRes.json();
  const controls = data.controls_state || {};
  const risk = data.risk_contract_state || {};
  const riskDiagnostic = riskData.risk_contract_diagnostic || {};
  const fresh = data.freshness_state || {};
  const packet = data.controls_review_packet || {};
  const matrix = data.controls_arming_matrix || {};
  document.getElementById('tlcLane').textContent = data.target_scope?.official_lane_key || 'BTCUSDT|8m|short|ladder_close_50_618';
  setBool('tlcFresh', fresh.fresh_cycle_valid);
  setBool('tlcRisk', risk.risk_contract_valid);
  setBool('tlcLive', controls.live_execution_enabled);
  setBool('tlcLaneAllowed', controls.official_lane_allowed);
  setBool('tlcKill', controls.kill_switch_allows_tiny_live);
  document.getElementById('tlcNext').textContent = packet.next_required_step || 'UNKNOWN';
  setBool('tlcForbidden', packet.submit_still_forbidden !== false);
  document.getElementById('tlcBlockers').textContent = (matrix.blocked_by || []).join(', ') || 'none';
  document.getElementById('tlcRiskReasons').textContent = (risk.risk_contract_invalid_reasons || []).join(', ') || 'none';
  document.getElementById('tlcRiskRootCause').textContent = riskDiagnostic.root_cause || 'unknown';
  document.getElementById('tlcRiskFixStatus').textContent = riskData.risk_contract_fix_overall_status || 'unknown';
  document.getElementById('tinyLiveControls').className = 'tiny-live-controls ' + (packet.next_required_step === 'R262_FINAL_SUBMIT_CONSOLE' ? 'ready' : 'blocked');
  document.getElementById('tlcRaw').textContent = JSON.stringify({
    status: data.status,
    overall: data.controls_arming_overall_status,
    recommended_next_operator_move: data.recommended_next_operator_move,
    safety: data.safety
  }, null, 2);
}

async function recordTinyLiveControlsReview() {
  const phrase = document.getElementById('tlcReviewPhrase').value;
  const operatorId = document.getElementById('operator')?.value || 'local_operator';
  const res = await fetch('/tiny-live/controls/review/record', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({confirm_tiny_live_controls_review: phrase, operator_id: operatorId})
  });
  const data = await res.json();
  document.getElementById('message').textContent = JSON.stringify(data, null, 2);
  await loadTinyLiveControls();
}

async function armTinyLiveControls() {
  const phrase = document.getElementById('tlcArmPhrase').value;
  const reason = document.getElementById('tlcArmReason').value;
  const operatorId = document.getElementById('operator')?.value || 'local_operator';
  const res = await fetch('/tiny-live/controls/arm', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({confirm_arm_tiny_live_controls: phrase, operator_id: operatorId, reason})
  });
  const data = await res.json();
  document.getElementById('message').textContent = JSON.stringify(data, null, 2);
  await loadTinyLiveControls();
}

async function loadTinyLiveFinalConsole() {
  const res = await fetch('/tiny-live/final-console');
  const data = await res.json();
  const contract = data.contract_fit_panel || {};
  const triplet = data.signed_triplet_panel || {};
  const controls = data.controls_panel || {};
  const lane = data.lane_intelligence_panel || {};
  const readiness = data.promotion_readiness_panel || {};
  const go = data.final_console_go_no_go_packet || {};
  const matrix = data.final_console_matrix || {};
  const exchange = data.exchange_minimum_decision_packet || {};
  document.getElementById('tlfLane').textContent = data.target_scope?.official_lane_key || 'BTCUSDT|8m|short|ladder_close_50_618';
  document.getElementById('tlfOverall').textContent = data.final_console_overall_status || 'UNKNOWN';
  setBool('tlfR262b', matrix.r262b_valid);
  setBool('tlfTriplet', triplet.signed_triplet_available);
  setBool('tlfControls', controls.controls_armed);
  document.getElementById('tlfLaneStatus').textContent = lane.execution_lane_timeframe_status || 'unknown';
  document.getElementById('tlfPromotionStatus').textContent = lane.execution_lane_promotion_status || 'unknown';
  document.getElementById('tlfReadiness').textContent = lane.readiness_status || 'UNKNOWN';
  setBool('tlfR264', go.go_for_r264_actual_submit_checkpoint);
  setBool('tlfForbidden', data.target_scope?.submit_allowed === false);
  document.getElementById('tlfExchangeReason').textContent = exchange.block_reason || 'none';
  document.getElementById('tlfExchangeMinNotional').textContent = exchange.minimum_valid_notional_after_rounding ?? 'unknown/not checked';
  document.getElementById('tlfConfiguredCap').textContent = exchange.configured_proper_tiny_cap_usdt ?? 'unknown';
  document.getElementById('tlfExchangeDecision').textContent = exchange.recommended_operator_decision || 'unknown';
  document.getElementById('tlfExchangeSummary').textContent = [
    `minimum quantity=${exchange.minimum_valid_quantity_after_rounding ?? 'unknown'}`,
    `wallet 126 enough=${exchange.wallet_supports_exchange_minimum_tiny ?? 'unknown/not checked'}`,
    `recommended cap=${exchange.recommended_cap_usdt ?? 'none'}`,
    `applied=${exchange.recommended_cap_applied === true ? 'true' : 'false'}`
  ].join('; ');
  document.getElementById('tlfExchangeCommand').textContent = exchange.safe_next_command || 'curl -s http://127.0.0.1:8015/tiny-live/final-console | jq .exchange_minimum_decision_packet';
  document.getElementById('tlfPromoted').textContent = (lane.promoted_lanes || []).join(', ') || 'none';
  document.getElementById('tlfBlockers').textContent = (readiness.readiness_blockers || []).join('; ') || 'none';
  document.getElementById('tlfWarning').textContent = (lane.warnings || []).join('; ') || 'none';
  document.getElementById('tlfNext').textContent = go.next_required_step || 'UNKNOWN';
  document.getElementById('tinyLiveFinalConsole').className = 'tiny-live-final-console ' + (go.go_for_r264_actual_submit_checkpoint ? 'ready' : 'blocked');
  document.getElementById('tlfRaw').textContent = JSON.stringify({
    status: data.status,
    contract_fit_panel: contract,
    signed_triplet_panel: triplet,
    controls_panel: controls,
    exchange_minimum_decision_packet: exchange,
    lane_intelligence_panel: lane,
    final_console_go_no_go_packet: go,
    safety: data.safety
  }, null, 2);
}

async function recordTinyLiveFinalConsoleReview() {
  const phrase = document.getElementById('tlfReviewPhrase').value;
  const operatorId = document.getElementById('operator')?.value || 'local_operator';
  const res = await fetch('/tiny-live/final-console/review/record', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({confirm_final_console_review: phrase, operator_id: operatorId})
  });
  const data = await res.json();
  document.getElementById('message').textContent = JSON.stringify(data, null, 2);
  await loadTinyLiveFinalConsole();
}

async function armTinyLiveFinalConsoleControls() {
  const phrase = document.getElementById('tlfArmPhrase').value;
  const reason = document.getElementById('tlfArmReason').value;
  const operatorId = document.getElementById('operator')?.value || 'local_operator';
  const res = await fetch('/tiny-live/final-console/controls/arm', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({confirm_final_console_controls_arming: phrase, operator_id: operatorId, reason})
  });
  const data = await res.json();
  document.getElementById('message').textContent = JSON.stringify(data, null, 2);
  await loadTinyLiveFinalConsole();
}

async function loadTinyLiveActualSubmit() {
  const res = await fetch('/tiny-live/actual-submit/reconcile');
  const data = await res.json();
  const pre = data.pre_submit_validation || {};
  const triplet = data.order_triplet_summary || {};
  const idem = data.idempotency || {};
  const rec = data.reconciliation || {};
  const recovery = data.partial_success_recovery_packet || {};
  const matrix = data.actual_submit_matrix || {};
  document.getElementById('tlaLane').textContent = data.target_scope?.official_lane_key || 'BTCUSDT|8m|short|ladder_close_50_618';
  document.getElementById('tlaOverall').textContent = data.actual_submit_overall_status || 'UNKNOWN';
  setBool('tlaValid', pre.valid);
  setBool('tlaArmed', matrix.r263_armed);
  setBool('tlaFresh', matrix.signed_triplet_fresh);
  setBool('tlaIdem', matrix.idempotency_clean);
  setBool('tlaExecuted', matrix.executed);
  setBool('tlaReconciled', matrix.reconciled);
  document.getElementById('tlaBlockers').textContent = (pre.blocked_by || []).join(', ') || 'none';
  document.getElementById('tlaTriplet').textContent = JSON.stringify(triplet);
  document.getElementById('tlaIdempotency').textContent = `${idem.actual_submit_idempotency_key || 'missing'} prior=${idem.prior_live_submit_found}`;
  document.getElementById('tlaReconciliation').textContent = `attempted=${rec.attempted} all_three=${rec.all_three_reconciled} partial=${rec.partial_success}`;
  document.getElementById('tlaRecovery').textContent = recovery.required ? recovery.operator_action : 'not required';
  document.getElementById('tinyLiveActualSubmit').className = 'tiny-live-actual-submit ' + (pre.valid ? 'ready' : 'blocked');
  document.getElementById('tlaCommand').textContent = 'PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward tiny-live-actual-submit-reconcile --execute-actual-live-submit --allow-binance-order-endpoint --confirm-actual-live-submit "I CONFIRM TINY LIVE BTCUSDT 8M SHORT ACTUAL SUBMIT; USE LATEST R262B CONTRACT-FIT SIGNED TRIPLET ONLY; MAIN SELL MARKET 0.006 BTC; STOP BUY STOP_MARKET REDUCE_ONLY; TAKE_PROFIT BUY TAKE_PROFIT_MARKET REDUCE_ONLY; NO OTHER ORDERS." --operator-id local_operator --reason "R264 actual tiny-live submit after R262B contract-fit and R263 final console arming."';
  document.getElementById('tlaRaw').textContent = JSON.stringify({
    status: data.status,
    input_summary: data.input_summary,
    pre_submit_validation: pre,
    submit_plan: data.submit_plan,
    submit_result: data.submit_result,
    reconciliation: rec,
    partial_success_recovery_packet: recovery,
    safety: data.safety
  }, null, 2);
}

async function recordTinyLiveActualSubmitDryPreview() {
  const phrase = document.getElementById('tlaDryPhrase').value;
  const operatorId = document.getElementById('operator')?.value || 'local_operator';
  const res = await fetch('/tiny-live/actual-submit/dry-preview', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({confirm_actual_submit_dry_preview: phrase, operator_id: operatorId})
  });
  const data = await res.json();
  document.getElementById('message').textContent = JSON.stringify(data, null, 2);
  await loadTinyLiveActualSubmit();
}

async function executeTinyLiveActualSubmit() {
  const phrase = document.getElementById('tlaLivePhrase').value;
  const reason = document.getElementById('tlaLiveReason').value;
  const allow = document.getElementById('tlaAllowEndpoint').checked;
  const operatorId = document.getElementById('operator')?.value || 'local_operator';
  const res = await fetch('/tiny-live/actual-submit/execute', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({confirm_actual_live_submit: phrase, allow_binance_order_endpoint: allow, operator_id: operatorId, reason})
  });
  const data = await res.json();
  document.getElementById('message').textContent = JSON.stringify(data, null, 2);
  await loadTinyLiveActualSubmit();
}

async function loadTinyLiveJitLaunchPacket() {
  const res = await fetch('/tiny-live/jit-launch-packet');
  const data = await res.json();
  const steps = data.jit_step_results || {};
  const r262b = steps.r262b_contract_fit_refresh || {};
  const r263 = steps.r263_runtime_arming || {};
  const r264 = steps.r264_dry_preview || {};
  const validation = data.jit_validation || {};
  const command = data.final_live_submit_command_packet || {};
  const go = data.jit_go_no_go_packet || {};
  const matrix = data.jit_launch_matrix || {};
  document.getElementById('tljLane').textContent = data.target_scope?.official_lane_key || 'BTCUSDT|8m|short|ladder_close_50_618';
  document.getElementById('tljOverall').textContent = data.jit_launch_overall_status || 'UNKNOWN';
  setBool('tljR262b', validation.r262b_valid || r262b.succeeded);
  setBool('tljR263', validation.r263_armed || r263.controls_armed);
  setBool('tljR264', validation.r264_dry_preview_valid || r264.succeeded);
  setBool('tljIdem', validation.idempotency_clean || r264.idempotency_clean);
  setBool('tljCommandAvailable', command.available);
  setBool('tljSubmitAllowed', data.target_scope?.submit_allowed === true);
  setBool('tljOrderPlaced', data.target_scope?.order_placed === true);
  setBool('tljRecorded', data.jit_launch_packet_recorded);
  document.getElementById('tljWarning').textContent = data.experimental_lane_warning?.message || '8m short experimental lane acceptance required.';
  document.getElementById('tljBlockers').textContent = (validation.blocked_by || matrix.blocked_by || []).join(', ') || 'none';
  document.getElementById('tljNext').textContent = go.next_required_step || 'UNKNOWN';
  document.getElementById('tljOperatorMove').textContent = data.recommended_next_operator_move || 'loading';
  document.getElementById('tljCommand').textContent = command.available ? command.command : 'Manual command unavailable until JIT packet is GO.';
  document.getElementById('tinyLiveJitLaunchPacket').className = 'tiny-live-jit-launch ' + (go.go_for_manual_live_submit_command ? 'ready' : 'blocked');
  document.getElementById('tljRaw').textContent = JSON.stringify({
    status: data.status,
    jit_step_results: steps,
    jit_validation: validation,
    final_live_submit_command_packet: command,
    jit_go_no_go_packet: go,
    jit_launch_matrix: matrix,
    safety: data.safety
  }, null, 2);
}

async function runTinyLiveJitLaunchPrep() {
  const phrase = document.getElementById('tljPhrase').value;
  const reason = document.getElementById('tljReason').value;
  const operatorId = document.getElementById('operator')?.value || 'local_operator';
  const record = document.getElementById('tljRecord').checked;
  const res = await fetch('/tiny-live/jit-launch-packet/run', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({confirm_jit_launch_prep: phrase, record_jit_launch_packet: record, operator_id: operatorId, reason})
  });
  const data = await res.json();
  document.getElementById('message').textContent = JSON.stringify(data, null, 2);
  await loadTinyLiveJitLaunchPacket();
  await loadTinyLiveFinalConsole();
  await loadTinyLiveActualSubmit();
}

async function loadHealth() {
  const res = await fetch('/health');
  const data = await res.json();
  document.getElementById('health').textContent = data.ok ? 'ok' : 'not ok';
  document.getElementById('live').textContent = String(data.live_execution_enabled);
}

async function loadReadiness() {
  const res = await fetch('/readiness');
  const data = await res.json();
  const state = data.current_state || {};
  const root = document.getElementById('readiness');
  const isReady = data.readiness_status === 'READY';
  root.className = 'readiness ' + (isReady ? 'ready' : 'not-ready');
  document.getElementById('readyStatus').textContent = data.readiness_status || 'UNKNOWN';
  document.getElementById('readyStatus').className = 'value ' + (isReady ? 'safe' : 'danger');
  document.getElementById('allowedNow').textContent = String(data.allowed_now === true);
  document.getElementById('allowedNow').className = 'value ' + (data.allowed_now === true ? 'safe' : 'danger');
  document.getElementById('freshEligible').textContent = String(state.fresh_eligible_count ?? 0);
  document.getElementById('outcomesToday').textContent = String(state.manual_outcomes_today ?? 0);
  document.getElementById('lossesToday').textContent = String(state.losses_today ?? 0);
  document.getElementById('pnlToday').textContent = String(state.pnl_usd_today ?? 0);
  document.getElementById('readinessLive').textContent = String(data.live_execution_enabled);
  document.getElementById('readinessOrder').textContent = String(data.order_placed);
  document.getElementById('readinessReason').textContent = data.reason_summary || '';
  document.getElementById('readinessBlockers').textContent = (data.blockers || []).length ? data.blockers.join('; ') : 'none';
  document.getElementById('nextAction').textContent = data.next_required_action || '';
  if (!isReady) {
    document.getElementById('readinessReason').textContent = (data.reason_summary || '') + ' Manual live trade should not be taken now.';
  }
}

async function loadTradeTicket() {
  const params = new URLSearchParams({
    latest_only: document.getElementById('latestOnly')?.checked ? 'true' : 'false',
    allow_short: document.getElementById('allowShort')?.checked ? 'true' : 'false'
  });
  const res = await fetch('/trade-ticket?' + params.toString());
  const data = await res.json();
  currentTicket = data;
  const status = data.ticket_status || 'BLOCKED';
  const proposed = status === 'PROPOSED';
  const root = document.getElementById('tradeTicket');
  root.className = 'ticket ' + (status === 'EXPIRED' ? 'expired' : (proposed ? 'proposed' : 'blocked'));
  document.getElementById('ticketStatus').textContent = status;
  document.getElementById('ticketStatus').className = 'value ' + (proposed ? 'safe' : 'danger');
  document.getElementById('ticketReadiness').textContent = data.readiness_status || 'UNKNOWN';
  document.getElementById('ticketReadiness').className = 'value ' + (data.readiness_status === 'READY' ? 'safe' : 'danger');
  document.getElementById('ticketAllowed').textContent = String(data.allowed_now === true);
  document.getElementById('ticketAllowed').className = 'value ' + (data.allowed_now === true ? 'safe' : 'danger');
  document.getElementById('ticketSignal').textContent = data.signal_id || 'n/a';
  document.getElementById('ticketDirection').textContent = `${data.direction || 'n/a'}/${data.timeframe || 'n/a'}`;
  document.getElementById('ticketEntry').textContent = String(data.entry ?? 'n/a');
  document.getElementById('ticketStop').textContent = String(data.stop ?? 'n/a');
  document.getElementById('ticketTakeProfit').textContent = String(data.take_profit ?? 'n/a');
  document.getElementById('ticketPosition').textContent = String(data.suggested_position_usd ?? 'n/a');
  document.getElementById('ticketLeverage').textContent = String(data.suggested_leverage ?? 'n/a');
  document.getElementById('ticketMaxLoss').textContent = String(data.max_loss_usd ?? 'n/a');
  document.getElementById('ticketMargin').textContent = data.margin_mode || 'isolated';
  document.getElementById('ticketLive').textContent = String(data.live_execution_enabled);
  document.getElementById('ticketOrder').textContent = String(data.order_placed);
  document.getElementById('ticketBlockers').textContent = (data.blockers || []).length ? data.blockers.join('; ') : 'none';
  document.getElementById('ticketReason').textContent = data.machine_reason || '';
  document.getElementById('approveTicketButton').disabled = !proposed;
  document.getElementById('executePaperButton').disabled = !proposed;
  document.getElementById('paperExecutionBlocked').style.display = proposed ? 'none' : 'block';
  document.getElementById('stubSubmitButton').disabled = !data.ticket_id;
}

async function loadExchangeDryRun() {
  const params = new URLSearchParams({
    allow_short: document.getElementById('allowShort')?.checked ? 'true' : 'false'
  });
  const res = await fetch('/exchange-dry-run?' + params.toString());
  const data = await res.json();
  const valid = data.validation_status === 'VALID';
  const root = document.getElementById('exchangeDryRun');
  root.className = 'exchange-dry-run ' + (valid ? 'proposed' : 'blocked');
  document.getElementById('dryRunStatus').textContent = data.validation_status || 'BLOCKED';
  document.getElementById('dryRunStatus').className = 'value ' + (valid ? 'safe' : 'danger');
  document.getElementById('dryRunExchange').textContent = data.exchange || 'n/a';
  document.getElementById('dryRunSymbol').textContent = data.symbol || 'n/a';
  document.getElementById('dryRunSide').textContent = data.side || 'n/a';
  document.getElementById('dryRunPositionSide').textContent = data.position_side || 'n/a';
  document.getElementById('dryRunNotional').textContent = String(data.notional_usd ?? 'n/a');
  document.getElementById('dryRunQuantity').textContent = String(data.quantity_rounded ?? 'n/a');
  document.getElementById('dryRunEntry').textContent = String(data.entry_price_rounded ?? 'n/a');
  document.getElementById('dryRunStop').textContent = String(data.stop_price_rounded ?? 'n/a');
  document.getElementById('dryRunTakeProfit').textContent = String(data.take_profit_price_rounded ?? 'n/a');
  document.getElementById('dryRunLeverage').textContent = String(data.leverage ?? 'n/a');
  document.getElementById('dryRunMargin').textContent = data.margin_mode || 'n/a';
  document.getElementById('dryRunLive').textContent = String(data.live_execution_enabled);
  document.getElementById('dryRunOrder').textContent = String(data.order_placed);
  document.getElementById('dryRunFlag').textContent = String(data.dry_run === true);
  document.getElementById('dryRunBlockers').textContent = (data.blockers || []).length ? data.blockers.join('; ') : 'none';
}

async function loadLiveSafety() {
  const params = new URLSearchParams({
    allow_short: document.getElementById('allowShort')?.checked ? 'true' : 'false'
  });
  const res = await fetch('/live-safety?' + params.toString());
  const data = await res.json();
  const allowed = data.live_safety_status === 'WOULD_BE_ALLOWED_IF_LIVE_ENABLED';
  const root = document.getElementById('liveSafety');
  root.className = 'live-safety ' + (allowed ? 'proposed' : 'blocked');
  document.getElementById('liveSafetyStatus').textContent = data.live_safety_status || 'BLOCKED';
  document.getElementById('liveSafetyStatus').className = 'value ' + (allowed ? 'safe' : 'danger');
  document.getElementById('liveSafetyEnabled').textContent = String(data.live_execution_enabled);
  document.getElementById('liveSafetyOrder').textContent = String(data.order_placed);
  document.getElementById('liveSafetyKill').textContent = String(data.kill_switch_active);
  document.getElementById('liveSafetyAllow').textContent = String(data.allow_live_orders);
  document.getElementById('liveSafetyBlockers').textContent = (data.blockers || []).length ? data.blockers.join('; ') : 'none';
  document.getElementById('liveSafetyFailed').textContent = (data.failed_gates || []).length ? data.failed_gates.join(', ') : 'none';
  document.getElementById('liveSafetyPassed').textContent = (data.passed_gates || []).length ? data.passed_gates.join(', ') : 'none';
  document.getElementById('liveSafetyNext').textContent = data.next_required_action || '';
  const protocol = data.protocol || {};
  document.getElementById('liveSafetyProtocol').textContent = `${protocol.max_position_usd ?? 44} USDT max, ${protocol.preferred_leverage ?? 2}x preferred, ${protocol.max_leverage ?? 3}x max, ${protocol.margin_mode || 'isolated'} margin, ${protocol.max_trades_per_day ?? 1} trade/day, ${protocol.hard_daily_stop || 'stop after -5 USDT or 1 loss'}.`;
  document.getElementById('connectorSafety').textContent = data.live_safety_status || 'BLOCKED';
  document.getElementById('connectorKill').textContent = String(data.kill_switch_active);
}

async function submitLiveConnectorStub() {
  if (!currentTicket || !currentTicket.ticket_id) return;
  const operatorInput = document.getElementById('operator');
  const notesInput = document.getElementById('ticketNotes');
  const body = {
    ticket_id: currentTicket.ticket_id,
    operator: operatorInput ? operatorInput.value || 'josue' : 'josue',
    notes: notesInput ? notesInput.value : ''
  };
  const res = await fetch('/live-connector/stub-submit', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body)
  });
  const data = await res.json();
  const message = document.getElementById('message');
  if (!res.ok) {
    message.className = 'feedback error';
    message.innerHTML = `<strong>API error ${res.status}</strong><pre>${esc(JSON.stringify(data, null, 2))}</pre>`;
  } else {
    message.className = 'feedback success';
    message.innerHTML = `<strong>Live connector stub attempt recorded:</strong> live_attempt_id=${esc(data.live_attempt_id)} | connector_mode=${esc(data.connector_mode)} | rejected=${esc(data.rejected)} | order_placed=${esc(data.order_placed)}`;
  }
  await loadLiveAttempts();
}

async function loadLiveAttempts() {
  const res = await fetch('/live-connector/attempts?limit=1');
  const data = await res.json();
  document.getElementById('connectorMode').textContent = data.connector_mode || 'stub_no_order';
  document.getElementById('connectorLive').textContent = String(data.live_execution_enabled);
  document.getElementById('connectorOrder').textContent = String(data.order_placed);
  const attempts = data.live_attempts || [];
  if (!attempts.length) {
    document.getElementById('lastLiveAttempt').textContent = 'none';
    return;
  }
  const latest = attempts[0];
  document.getElementById('lastLiveAttempt').textContent = `${latest.created_at} | ${latest.live_attempt_id} | rejected=${latest.rejected} | order_placed=${latest.order_placed}`;
}

async function loadBinanceReadonlyStatus() {
  const res = await fetch('/binance-readonly/status');
  const data = await res.json();
  const ready = data.connector_status === 'READY_READ_ONLY';
  const root = document.getElementById('binanceReadonly');
  root.className = 'binance-readonly ' + (ready ? 'proposed' : 'blocked');
  document.getElementById('binanceStatus').textContent = data.connector_status || 'MISSING_ENV';
  document.getElementById('binanceStatus').className = 'value ' + (ready ? 'safe' : 'danger');
  document.getElementById('binanceMode').textContent = data.connector_mode || 'n/a';
  document.getElementById('binanceApiKeyPresent').textContent = String(data.api_key_present === true);
  document.getElementById('binanceApiSecretPresent').textContent = String(data.api_secret_present === true);
  document.getElementById('binanceApiKeyPreview').textContent = data.api_key_preview || 'n/a';
  document.getElementById('binanceLiveTradingEnv').textContent = data.live_trading_env || 'n/a';
  document.getElementById('binanceLive').textContent = String(data.live_execution_enabled);
  document.getElementById('binanceOrder').textContent = String(data.order_placed);
  document.getElementById('binanceBlockers').textContent = (data.blockers || []).length ? data.blockers.join('; ') : 'none';
  document.getElementById('binanceForbidden').textContent = (data.forbidden_actions || []).join(', ');
}

async function loadBinanceLiveConnector() {
  const statusRes = await fetch('/binance-live/connector-status');
  const status = await statusRes.json();
  const attemptsRes = await fetch('/binance-live/connector-attempts?limit=1');
  const attempts = await attemptsRes.json();
  const protectiveRes = await fetch('/binance-live/protective-status');
  const protective = await protectiveRes.json();
  const latest = (attempts.binance_live_connector_attempts || [])[0] || {};
  document.getElementById('binanceLiveConnectorMode').textContent = status.connector_mode || 'DRY_RUN_ONLY';
  document.getElementById('binanceLiveConnectorReadiness').textContent = status.readiness || 'BLOCKED';
  document.getElementById('binanceLiveConnectorKey').textContent = String(status.api_key_present === true);
  document.getElementById('binanceLiveConnectorSecret').textContent = String(status.api_secret_present === true);
  document.getElementById('binanceLiveConnectorTestNetwork').textContent = String(status.test_order_network_enabled === true);
  document.getElementById('binanceLiveConnectorSigning').textContent = String(status.signing_available === true);
  document.getElementById('binanceLiveConnectorAdapter').textContent = String(status.live_order_adapter_configured === true);
  document.getElementById('binanceLiveConnectorProtective').textContent = String(status.protective_orders_supported === true);
  document.getElementById('binanceLiveConnectorProtectiveRequired').textContent = String(protective.protective_orders_required === true);
  document.getElementById('binanceLiveConnectorProtectiveReady').textContent = String(protective.protective_orders_ready === true);
  document.getElementById('binanceLiveConnectorProtectiveMode').textContent = protective.protective_order_mode || 'PREVIEW_ONLY';
  document.getElementById('binanceLiveConnectorProtectiveTypes').textContent = `${protective.protective_stop_order_type || 'STOP_MARKET'} / ${protective.protective_take_profit_order_type || 'TAKE_PROFIT_MARKET'}`;
  document.getElementById('binanceLiveConnectorRealEndpoint').textContent = String(status.real_live_endpoint_prepared === true);
  document.getElementById('binanceLiveConnectorLive').textContent = String(status.live_execution_enabled === true);
  document.getElementById('binanceLiveConnectorAllow').textContent = String(status.allow_live_orders === true);
  document.getElementById('binanceLiveConnectorKill').textContent = String(status.global_kill_switch === true);
  document.getElementById('binanceLiveConnectorLatest').textContent = latest.attempt_id || 'none';
  document.getElementById('binanceLiveConnectorPreview').textContent = latest.status || 'none';
  document.getElementById('binanceLiveConnectorBlockers').textContent = (status.blockers || []).length ? status.blockers.join('; ') : 'none';
}

async function loadStrategyPerformance() {
  const res = await fetch('/strategy-performance/live-eligibility');
  const data = await res.json();
  const eligible = data.eligible_recommendations || [];
  const top = eligible[0] || (data.recommendations || [])[0] || {};
  document.getElementById('strategyExecution').textContent = String(data.execution_enabled === true);
  document.getElementById('strategyOrder').textContent = String(data.order_placed === true);
  document.getElementById('strategyPayload').textContent = String(data.no_order_payload_created === true);
  document.getElementById('strategyEligibleCount').textContent = String(eligible.length);
  document.getElementById('strategyTopRecommendation').textContent = top.timeframe
    ? `${top.timeframe} ${top.direction || 'n/a'} ${top.entry_mode || 'n/a'}: ${top.recommendation}`
    : 'none';
}

async function loadStrategyPromotion() {
  const res = await fetch('/strategy-promotion/status');
  const data = await res.json();
  const near = data.near_promotion || [];
  const ready = data.promotion_ready || [];
  const latest = data.latest_promotion_event || {};
  const formatRow = row => row.strategy_key
    ? `${row.strategy_key}: samples=${row.sample_count}/${row.required_sample_count} ${row.event_type}`
    : 'none';
  document.getElementById('promotionNearCount').textContent = String(near.length);
  document.getElementById('promotionReadyCount').textContent = String(ready.length);
  document.getElementById('promotionLatest').textContent = latest.event_id || 'none';
  document.getElementById('promotionNearTop').textContent = formatRow(near[0] || {});
  document.getElementById('promotionReadyTop').textContent = formatRow(ready[0] || {});
}

async function loadLivePreflight() {
  const res = await fetch('/live-preflight/promoted-strategy');
  const data = await res.json();
  const packsRes = await fetch('/live-preflight/packs?limit=1');
  const packsData = await packsRes.json();
  const latest = (packsData.live_preflight_packs || [])[0] || {};
  document.getElementById('preflightStatus').textContent = data.preflight_status || 'UNKNOWN';
  document.getElementById('preflightPromotedReady').textContent = String(data.promoted_strategy_ready === true);
  document.getElementById('preflightSignalFound').textContent = String(data.matching_fresh_signal_found === true);
  document.getElementById('preflightLatest').textContent = latest.preflight_id || 'none';
  document.getElementById('preflightStrategy').textContent = data.strategy_key || 'none';
  document.getElementById('preflightSignal').textContent = data.candidate_signal_id || 'none';
  document.getElementById('preflightNextAction').textContent = data.operator_next_action || 'n/a';
}

async function loadFirstLiveRunbook() {
  const res = await fetch('/first-live/runbook');
  const data = await res.json();
  const checklist = data.checklist || {};
  const passed = Object.values(checklist).filter(item => item && item.passed === true).length;
  const total = Object.keys(checklist).length;
  document.getElementById('firstLiveRunbookStatus').textContent = data.runbook_status || 'WAITING_FOR_PROMOTED_SIGNAL';
  document.getElementById('firstLiveGateDecision').textContent = data.gate_decision || 'NO_GO';
  document.getElementById('firstLiveSignalId').textContent = data.signal_id || 'none';
  document.getElementById('firstLiveChecklist').textContent = `${passed}/${total}`;
  document.getElementById('firstLiveBlockers').textContent = (data.blockers || []).length ? data.blockers.slice(0, 6).join('; ') : 'none';
  document.getElementById('firstLivePlan').textContent = (data.enablement_plan || []).length ? `${data.enablement_plan.length} manual steps` : 'none';
}

async function loadNotificationStatus() {
  const res = await fetch('/notifications/status');
  const data = await res.json();
  document.getElementById('notificationTelegramEnabled').textContent = String(data.telegram_enabled === true);
  document.getElementById('notificationTelegramConfigured').textContent = String(data.telegram_configured === true);
  document.getElementById('notificationAlertsRecorded').textContent = String(data.alerts_recorded ?? 0);
  document.getElementById('notificationLive').textContent = String(data.live_execution_enabled);
  document.getElementById('notificationOrder').textContent = String(data.order_placed);
  const lastAlert = data.last_alert;
  document.getElementById('notificationLastAlert').textContent = lastAlert
    ? `${lastAlert.created_at} | ${lastAlert.alert_type} | signal=${lastAlert.signal_id || 'n/a'}`
    : 'none';
}

async function checkNotifications(send, channel) {
  const res = await fetch('/notifications/check', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({send, channel})
  });
  const data = await res.json();
  const root = document.getElementById('notificationCheckResult');
  const message = document.getElementById('message');
  const telegram = data.telegram || {};
  root.textContent = `would_alert=${data.would_alert === true} alert_type=${data.alert_type || 'none'} telegram_status=${telegram.status || 'not_requested'} recorded=${data.recorded === true}`;
  if (!res.ok) {
    message.className = 'feedback error';
    message.innerHTML = `<strong>API error ${res.status}</strong><pre>${esc(JSON.stringify(data, null, 2))}</pre>`;
  } else {
    message.className = 'feedback';
    message.textContent = `Notification check complete. would_alert=${data.would_alert === true}. order_placed=${data.order_placed}.`;
  }
  await loadNotificationStatus();
}

async function loadAltWatchlist() {
  const summaryRes = await fetch('/watchlist/summary');
  const summary = await summaryRes.json();
  document.getElementById('watchlistBtcLiveOnly').textContent = String(summary.btc_live_only === true);
  document.getElementById('watchlistTotalSymbols').textContent = String(summary.total_symbols ?? 0);
  document.getElementById('watchlistLiveEligible').textContent = (summary.live_eligible_symbols || []).join(', ') || 'none';
  document.getElementById('watchlistPaperSymbols').textContent = String((summary.paper_watch_symbols || []).length);
  document.getElementById('watchlistRelativeSymbols').textContent = (summary.relative_strength_symbols || []).join(', ') || 'none';
  document.getElementById('watchlistKeyPair').textContent = summary.key_rotation_pair || 'ETHBTC';
  document.getElementById('watchlistPromotion').textContent = summary.next_promotion_candidate || 'ETHUSDT';
  document.getElementById('watchlistWarning').textContent = summary.warning || 'ETHUSDT, ETHBTC, and alts are paper/watch-only in R30';

  const listRes = await fetch('/watchlist?limit=10');
  const list = await listRes.json();
  const records = list.symbols || [];
  const root = document.getElementById('watchlistSymbols');
  if (!records.length) {
    root.innerHTML = '<div class="alt-watchlist">No watchlist symbols configured.</div>';
    return;
  }
  root.innerHTML = records.map(record => `<div class="alt-watchlist">
    <div class="grid">
      <div><div class="label">symbol</div><div class="value mono">${esc(record.symbol)}</div></div>
      <div><div class="label">category</div><div class="value">${esc(record.category)}</div></div>
      <div><div class="label">watch score</div><div class="value">${esc(record.watch_score)}</div></div>
      <div><div class="label">pair_type</div><div class="value">${esc(record.pair_type)}</div></div>
      <div><div class="label">permission</div><div class="value">${esc(record.current_phase_permission)}</div></div>
      <div><div class="label">live_eligible_symbol</div><div class="value ${record.live_eligible_symbol ? 'safe' : 'danger'}">${esc(record.live_eligible_symbol)}</div></div>
      <div><div class="label">paper_watch_enabled</div><div class="value safe">${esc(record.paper_watch_enabled)}</div></div>
    </div>
  </div>`).join('');
}

async function loadMultiSymbolSummary() {
  const res = await fetch('/multi-symbol/summary');
  const data = await res.json();
  document.getElementById('multiSymbolLive').textContent = String(data.live_execution_enabled);
  document.getElementById('multiSymbolOrder').textContent = String(data.order_placed);
  document.getElementById('multiSymbolBtcOnly').textContent = String(data.btc_live_only === true);
  document.getElementById('multiSymbolScanned').textContent = String(data.scanned_symbols ?? 0);
  document.getElementById('multiSymbolArchived').textContent = String(data.archived_records ?? 0);
  document.getElementById('multiSymbolKeyPair').textContent = data.key_rotation_pair || 'ETHBTC';
  document.getElementById('multiSymbolPromotion').textContent = data.next_promotion_candidate || 'ETHUSDT';
  renderMultiSymbolTopRanked(data.top_ranked_symbols || []);
}

function renderMultiSymbolTopRanked(records) {
  const root = document.getElementById('multiSymbolTopRanked');
  if (!records.length) {
    root.innerHTML = '<div class="multi-symbol-scanner">No ranked symbols.</div>';
    return;
  }
  root.innerHTML = records.map(record => `<div class="multi-symbol-scanner">
    <div class="grid">
      <div><div class="label">symbol</div><div class="value mono">${esc(record.symbol)}</div></div>
      <div><div class="label">status</div><div class="value">${esc(record.paper_signal_status)}</div></div>
      <div><div class="label">score/tier</div><div class="value">${esc(record.score)} / ${esc(record.tier)}</div></div>
      <div><div class="label">direction/timeframe</div><div class="value">${esc(record.direction)}/${esc(record.timeframe || 'n/a')}</div></div>
      <div><div class="label">permission</div><div class="value">${esc(record.current_phase_permission)}</div></div>
      <div><div class="label">live_eligible_symbol</div><div class="value ${record.live_eligible_symbol ? 'safe' : 'danger'}">${esc(record.live_eligible_symbol)}</div></div>
      <div><div class="label">order_placed</div><div class="value danger">${esc(record.order_placed)}</div></div>
    </div>
  </div>`).join('');
}

async function runMultiSymbolScan(write) {
  const res = await fetch(`/multi-symbol/scan?limit=20&write=${write ? 'true' : 'false'}`);
  const data = await res.json();
  const result = document.getElementById('multiSymbolScanResult');
  const message = document.getElementById('message');
  result.textContent = `scanned_symbols=${data.scanned_symbols ?? 0} write=${data.write === true} order_placed=${data.order_placed}`;
  renderMultiSymbolTopRanked(data.records || []);
  if (!res.ok) {
    message.className = 'feedback error';
    message.innerHTML = `<strong>API error ${res.status}</strong><pre>${esc(JSON.stringify(data, null, 2))}</pre>`;
  } else {
    message.className = 'feedback';
    message.textContent = `Multi-symbol paper scan complete. write=${data.write === true}. order_placed=${data.order_placed}.`;
  }
  await loadMultiSymbolSummary();
}

async function loadMarketIntelligence(write) {
  const res = await fetch(`/market-intelligence/summary?limit=10&write=${write ? 'true' : 'false'}`);
  const data = await res.json();
  document.getElementById('marketIntelLive').textContent = String(data.live_execution_enabled);
  document.getElementById('marketIntelOrder').textContent = String(data.order_placed);
  document.getElementById('marketIntelStatus').textContent = data.market_data_status || 'UNKNOWN';
  document.getElementById('marketIntelNetwork').textContent = String(data.network_used === true);
  document.getElementById('marketIntelKeyPair').textContent = data.key_rotation_pair || 'ETHBTC';
  document.getElementById('marketIntelRotationState').textContent = data.ethbtc_rotation_state || 'UNKNOWN';
  document.getElementById('marketIntelWarning').textContent = data.warning || 'market intelligence is public/read-only and paper/watch-only';
  renderMarketIntelTopRanked(data.symbols || []);
  await loadEthbtcRotation();
}

function renderMarketIntelTopRanked(records) {
  const root = document.getElementById('marketIntelTopRanked');
  if (!records.length) {
    root.innerHTML = '<div class="market-intelligence">No market intelligence records.</div>';
    return;
  }
  root.innerHTML = records.slice(0, 8).map(record => `<div class="market-intelligence">
    <div class="grid">
      <div><div class="label">symbol</div><div class="value mono">${esc(record.symbol)}</div></div>
      <div><div class="label">score</div><div class="value">${esc(record.market_intelligence_score)}</div></div>
      <div><div class="label">24h change</div><div class="value">${esc(record.price_change_percent_24h ?? 'n/a')}</div></div>
      <div><div class="label">market status</div><div class="value">${esc(record.market_data_status)}</div></div>
      <div><div class="label">permission</div><div class="value">${esc(record.current_phase_permission)}</div></div>
      <div><div class="label">live_eligible_symbol</div><div class="value ${record.live_eligible_symbol ? 'safe' : 'danger'}">${esc(record.live_eligible_symbol)}</div></div>
    </div>
  </div>`).join('');
}

async function loadEthbtcRotation() {
  const res = await fetch('/market-intelligence/rotation');
  const data = await res.json();
  document.getElementById('ethbtcPrice').textContent = String(data.ethbtc_price ?? 'n/a');
  document.getElementById('ethbtcChange').textContent = String(data.ethbtc_change_percent_24h ?? 'n/a');
  document.getElementById('ethbtcRotationState').textContent = data.rotation_state || 'UNKNOWN';
  document.getElementById('ethbtcInterpretation').textContent = data.interpretation || '';
}

async function loadEthPaperSummary() {
  const res = await fetch('/eth-paper/summary');
  const data = await res.json();
  document.getElementById('ethPaperLive').textContent = String(data.live_execution_enabled);
  document.getElementById('ethPaperOrder').textContent = String(data.order_placed);
  document.getElementById('ethPaperSymbol').textContent = data.symbol || 'ETHUSDT';
  document.getElementById('ethPaperRotationPair').textContent = data.rotation_pair || 'ETHBTC';
  document.getElementById('ethPaperRotationState').textContent = data.current_rotation_state || 'UNKNOWN';
  const latest = data.latest_candidate;
  document.getElementById('ethPaperLatest').textContent = latest
    ? `${latest.created_at} | ${latest.paper_candidate_status} | ${latest.direction} | score=${latest.score}`
    : 'none';
}

async function loadEthPaperCandidate(write) {
  const res = await fetch(`/eth-paper/candidate?use_network=false&write=${write ? 'true' : 'false'}`);
  const data = await res.json();
  document.getElementById('ethPaperLive').textContent = String(data.live_execution_enabled);
  document.getElementById('ethPaperOrder').textContent = String(data.order_placed);
  document.getElementById('ethPaperSymbol').textContent = data.symbol || 'ETHUSDT';
  document.getElementById('ethPaperRotationPair').textContent = data.rotation_pair || 'ETHBTC';
  document.getElementById('ethPaperRotationState').textContent = data.ethbtc_rotation_state || 'UNKNOWN';
  document.getElementById('ethPaperTierStatus').textContent = `${data.tier || 'n/a'} / ${data.paper_candidate_status || 'n/a'}`;
  document.getElementById('ethPaperDirection').textContent = data.direction || 'unknown';
  document.getElementById('ethPaperScore').textContent = String(data.score ?? 'n/a');
  document.getElementById('ethPaperReason').textContent = data.reason || '';
  const message = document.getElementById('message');
  if (!res.ok) {
    message.className = 'feedback error';
    message.innerHTML = `<strong>API error ${res.status}</strong><pre>${esc(JSON.stringify(data, null, 2))}</pre>`;
  } else {
    message.className = 'feedback';
    message.textContent = `ETH paper candidate checked. write=${data.write === true}. order_placed=${data.order_placed}.`;
  }
  await loadEthPaperSummary();
}

async function loadEthPaperOutcomeSummary() {
  const res = await fetch('/eth-paper/outcome-summary');
  const data = await res.json();
  document.getElementById('ethOutcomeLive').textContent = String(data.live_execution_enabled);
  document.getElementById('ethOutcomeOrder').textContent = String(data.order_placed);
  document.getElementById('ethOutcomeSymbol').textContent = data.symbol || 'ETHUSDT';
  document.getElementById('ethOutcomeRotationPair').textContent = data.rotation_pair || 'ETHBTC';
  document.getElementById('ethOutcomeTotal').textContent = String(data.total_outcomes ?? 0);
  document.getElementById('ethOutcomeWins').textContent = String(data.win_count ?? 0);
  document.getElementById('ethOutcomeLosses').textContent = String(data.loss_count ?? 0);
  document.getElementById('ethOutcomeOpen').textContent = String(data.open_count ?? 0);
  document.getElementById('ethOutcomeUnresolved').textContent = String(data.unresolved_count ?? 0);
  document.getElementById('ethOutcomeNoData').textContent = String(data.no_data_count ?? 0);
  document.getElementById('ethOutcomeRotationState').textContent = data.current_rotation_state || 'UNKNOWN';
  const latest = data.latest_outcome;
  document.getElementById('ethOutcomeLatest').textContent = latest
    ? `${latest.created_at} | ${latest.outcome_status} | ${latest.candidate_direction} | candidate=${latest.candidate_id}`
    : 'none';
}

async function loadEthPaperOutcome(write) {
  const res = await fetch(`/eth-paper/outcome?write=${write ? 'true' : 'false'}`);
  const data = await res.json();
  document.getElementById('ethOutcomeLive').textContent = String(data.live_execution_enabled);
  document.getElementById('ethOutcomeOrder').textContent = String(data.order_placed);
  document.getElementById('ethOutcomeSymbol').textContent = data.symbol || 'ETHUSDT';
  document.getElementById('ethOutcomeRotationPair').textContent = data.rotation_pair || 'ETHBTC';
  const message = document.getElementById('message');
  if (!res.ok) {
    message.className = 'feedback error';
    message.innerHTML = `<strong>API error ${res.status}</strong><pre>${esc(JSON.stringify(data, null, 2))}</pre>`;
  } else {
    message.className = 'feedback';
    message.textContent = `ETH paper outcome checked. write=${data.write === true}. order_placed=${data.order_placed}. status=${data.outcome_status}.`;
  }
  await loadEthPaperOutcomeSummary();
}

async function loadPaperRefreshStatus() {
  const res = await fetch('/paper-refresh/status');
  const data = await res.json();
  document.getElementById('paperRefreshLive').textContent = String(data.live_execution_enabled);
  document.getElementById('paperRefreshOrder').textContent = String(data.order_placed);
  document.getElementById('paperRefreshBtcOnly').textContent = String(data.btc_live_only === true);
  document.getElementById('paperRefreshTasks').textContent = (data.available_tasks || []).join(', ');
  document.getElementById('paperRefreshRuns').textContent = String(data.runs_recorded ?? 0);
  document.getElementById('paperRefreshPoll').textContent = String(data.configured_poll_seconds ?? 'n/a');
  document.getElementById('paperRefreshService').textContent = data.service_name || 'hammer-paper-refresh.service';
  document.getElementById('paperRefreshEntrypoint').textContent = data.watcher_entrypoint || 'n/a';
  const last = data.last_run;
  document.getElementById('paperRefreshLastRun').textContent = last
    ? `${last.created_at} | completed=${(last.completed_tasks || []).length} | failed=${(last.failed_tasks || []).length}`
    : 'none';
}

async function runPaperRefresh(sendNotifications) {
  const res = await fetch('/paper-refresh/run', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      use_network: false,
      write_outputs: true,
      send_notifications: sendNotifications === true
    })
  });
  const data = await res.json();
  const message = document.getElementById('message');
  if (!res.ok) {
    message.className = 'feedback error';
    message.innerHTML = `<strong>API error ${res.status}</strong><pre>${esc(JSON.stringify(data, null, 2))}</pre>`;
  } else {
    message.className = 'feedback';
    message.textContent = `Paper refresh complete. completed=${(data.completed_tasks || []).length}. failed=${(data.failed_tasks || []).length}. order_placed=${data.order_placed}.`;
  }
  await loadPaperRefreshStatus();
}

async function loadBetrayalShadowOutcomes() {
  const res = await fetch('/betrayal-shadow/outcomes?limit=5');
  const data = await res.json();
  const summary = data.summary || {};
  const root = document.getElementById('betrayalShadow');
  root.className = 'betrayal-shadow blocked';
  document.getElementById('betrayalShadowOnly').textContent = String(data.shadow_only === true);
  document.getElementById('betrayalShadowLive').textContent = String(data.live_execution_enabled === true);
  document.getElementById('betrayalShadowOrder').textContent = String(data.order_placed === true);
  document.getElementById('betrayalShadowTotal').textContent = String(summary.total_records ?? 0);
  document.getElementById('betrayalShadowWins').textContent = String(summary.wins ?? 0);
  document.getElementById('betrayalShadowLosses').textContent = String(summary.losses ?? 0);
  document.getElementById('betrayalShadowUnknown').textContent = String(summary.unresolved_no_data ?? 0);
  document.getElementById('betrayalShadowWinRate').textContent = summary.win_rate == null ? 'n/a' : String(summary.win_rate);
  document.getElementById('betrayalShadowAvgPnl').textContent = summary.avg_shadow_pnl_pct == null ? 'n/a' : String(summary.avg_shadow_pnl_pct);
  const records = data.records || [];
  const recordsRoot = document.getElementById('betrayalShadowRecords');
  if (!records.length) {
    recordsRoot.innerHTML = '<div class="betrayal-shadow">No betrayal shadow outcome records.</div>';
    return;
  }
  recordsRoot.innerHTML = records.map(record => {
    const comparison = record.comparison || {};
    const comparisonText = comparison.shadow_better ? 'shadow_better' : (comparison.original_better ? 'original_better' : 'inconclusive');
    return `<div class="betrayal-shadow">
      <div class="grid">
        <div><div class="label">original signal</div><div class="value mono">${esc(record.original_signal_id)}</div></div>
        <div><div class="label">original direction</div><div class="value">${esc(record.original_direction)}</div></div>
        <div><div class="label">shadow direction</div><div class="value">${esc(record.shadow_direction)}</div></div>
        <div><div class="label">betrayal score/tier</div><div class="value">${esc(record.betrayal_score)} / ${esc(record.betrayal_tier)}</div></div>
        <div><div class="label">shadow status</div><div class="value">${esc(record.shadow_status)}</div></div>
        <div><div class="label">comparison</div><div class="value">${esc(comparisonText)}</div></div>
        <div><div class="label">live_execution_enabled</div><div class="value danger">${esc(record.live_execution_enabled)}</div></div>
        <div><div class="label">order_placed</div><div class="value danger">${esc(record.order_placed)}</div></div>
      </div>
    </div>`;
  }).join('');
}

async function trackBetrayalShadows() {
  const body = {
    latest_only: document.getElementById('latestOnly')?.checked !== false,
    limit: Number(document.getElementById('limit')?.value || 20),
    since_hours: 24,
    min_betrayal_score: 50
  };
  const res = await fetch('/betrayal-shadow/track', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body)
  });
  const data = await res.json();
  const message = document.getElementById('message');
  if (!res.ok) {
    message.className = 'feedback error';
    message.innerHTML = `<strong>API error ${res.status}</strong><pre>${esc(JSON.stringify(data, null, 2))}</pre>`;
  } else {
    message.className = 'feedback success';
    message.innerHTML = `<strong>Betrayal shadows tracked:</strong> created=${esc(data.created)} | updated=${esc(data.updated)} | shadow_only=${esc(data.shadow_only)} | order_placed=${esc(data.order_placed)}`;
  }
  await loadBetrayalShadowOutcomes();
}

async function loadCandidates() {
  const params = new URLSearchParams({
    latest_only: document.getElementById('latestOnly').checked ? 'true' : 'false',
    allow_short: document.getElementById('allowShort').checked ? 'true' : 'false',
    limit: document.getElementById('limit').value || '10'
  });
  const res = await fetch('/candidates?' + params.toString());
  const data = await res.json();
  document.getElementById('archive').textContent = data.archive_log_dir || 'n/a';
  document.getElementById('generated').textContent = data.generated_at || 'n/a';
  document.getElementById('live').textContent = String(data.live_execution_enabled);
  document.getElementById('order').textContent = String(data.order_placed);
  currentCandidates = data.candidates || [];
  const eligibleOnly = document.getElementById('eligibleOnly').checked;
  const includeForbidden = document.getElementById('includeForbidden').checked;
  const visible = currentCandidates.filter(c => {
    if (eligibleOnly && c.decision !== 'ELIGIBLE_TINY_LIVE') return false;
    if (!includeForbidden && c.decision === 'FORBIDDEN') return false;
    return true;
  });
  const root = document.getElementById('candidates');
  if (visible.length === 0) {
    root.innerHTML = '<div class="candidate">No candidates returned.</div>';
    return;
  }
  root.innerHTML = visible.map(c => renderCandidate(c, currentCandidates.indexOf(c))).join('');
}

function decisionClass(decision) {
  if (decision === 'ELIGIBLE_TINY_LIVE') return 'eligible';
  if (decision === 'PAPER_ONLY') return 'paper';
  if (decision === 'FORBIDDEN') return 'forbidden';
  return 'paper';
}

function renderCandidate(c, index) {
  const cls = decisionClass(c.decision);
  const canApprove = c.decision === 'ELIGIBLE_TINY_LIVE';
  const disabledText = c.decision === 'FORBIDDEN'
    ? 'Blocked: candidate is FORBIDDEN'
    : 'Blocked: candidate is PAPER_ONLY';
  return `<section class="candidate candidate-${cls}">
    <div><span class="badge badge-${cls}">${esc(c.decision)}</span></div>
    <div class="grid">
      <div><div class="label">signal_id</div><div class="value mono">${esc(c.signal_id)}</div></div>
      <div><div class="label">decision</div><div class="value">${esc(c.decision)}</div></div>
      <div><div class="label">reason</div><div class="value">${esc(c.reason)}</div></div>
      <div><div class="label">direction/timeframe</div><div class="value">${esc(c.direction)}/${esc(c.timeframe)}</div></div>
      <div><div class="label">entry</div><div class="value">${esc(c.entry)}</div></div>
      <div><div class="label">stop</div><div class="value">${esc(c.stop)}</div></div>
      <div><div class="label">take_profit</div><div class="value">${esc(c.take_profit)}</div></div>
      <div><div class="label">age_minutes</div><div class="value">${esc(c.age_minutes)}</div></div>
      <div><div class="label">freshness_status</div><div class="value">${esc(c.freshness_status)}</div></div>
      <div><div class="label">capped_max_position_size_usd</div><div class="value">${esc(c.capped_max_position_size_usd)}</div></div>
      <div><div class="label">suggested_leverage</div><div class="value">${esc(c.suggested_leverage)}</div></div>
      <div><div class="label">score/tier</div><div class="value">${esc(c.score)} / ${esc(c.tier)}</div></div>
      <div><div class="label">live_execution_enabled</div><div class="value danger">${esc(c.live_execution_enabled)}</div></div>
      <div><div class="label">order_placed</div><div class="value danger">${esc(c.order_placed)}</div></div>
    </div>
    <p><input id="notes-${index}" class="notes" placeholder="notes"></p>
    <div class="button-row">
      <button onclick="recordDecision(${index}, 'watch')">Watch</button>
      <button class="reject" onclick="recordDecision(${index}, 'reject')">Reject</button>
      <button onclick="recordDecision(${index}, 'paper_only')">Paper Only</button>
      <button class="approve" onclick="recordDecision(${index}, 'approve_manual_live')" ${canApprove ? '' : 'disabled'} title="${canApprove ? 'Record approval intent only' : disabledText}">Log Manual-Live Intent</button>
    </div>
    ${canApprove ? '' : `<div class="muted">${disabledText}. Watch / Reject / Paper Only remain available.</div>`}
  </section>`;
}

async function approvePaperTicket() {
  if (!currentTicket || !currentTicket.ticket_id) return;
  const operatorInput = document.getElementById('operator');
  const notesInput = document.getElementById('ticketNotes');
  const body = {
    ticket_id: currentTicket.ticket_id,
    operator: operatorInput ? operatorInput.value || 'josue' : 'josue',
    notes: notesInput ? notesInput.value : '',
    ticket_snapshot: currentTicket
  };
  const res = await fetch('/trade-ticket/approve-paper', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body)
  });
  const data = await res.json();
  const message = document.getElementById('message');
  if (!res.ok) {
    message.className = 'feedback error';
    message.innerHTML = `<strong>API error ${res.status}</strong><pre>${esc(JSON.stringify(data, null, 2))}</pre>`;
  } else {
    message.className = 'feedback success';
    message.innerHTML = `<strong>Paper ticket approval intent recorded:</strong> ticket_id=${esc(data.ticket.ticket_id)} | order_placed=${esc(data.order_placed)} | paper_order_placed=${esc(data.paper_order_placed)}`;
  }
}

async function executePaperTicket() {
  if (!currentTicket || !currentTicket.ticket_id) return;
  const operatorInput = document.getElementById('operator');
  const notesInput = document.getElementById('ticketNotes');
  const body = {
    ticket_id: currentTicket.ticket_id,
    operator: operatorInput ? operatorInput.value || 'josue' : 'josue',
    notes: notesInput ? notesInput.value : ''
  };
  const res = await fetch('/trade-ticket/execute-paper', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body)
  });
  const data = await res.json();
  const message = document.getElementById('message');
  if (!res.ok) {
    message.className = 'feedback error';
    message.innerHTML = `<strong>API error ${res.status}</strong><pre>${esc(JSON.stringify(data, null, 2))}</pre>`;
  } else {
    message.className = 'feedback success';
    message.innerHTML = `<strong>Paper execution recorded:</strong> paper_execution_id=${esc(data.paper_execution_id)} | paper_order_placed=${esc(data.paper_order_placed)} | order_placed=${esc(data.order_placed)} | live_execution_enabled=${esc(data.live_execution_enabled)}`;
  }
  await loadPaperExecutions();
}

function recordTicketWatch() {
  const message = document.getElementById('message');
  message.className = 'feedback';
  message.textContent = 'Ticket marked for watch/reject in operator console only. No order will be placed.';
}

async function loadPaperExecutions() {
  const res = await fetch('/paper-executions?limit=10');
  const data = await res.json();
  const root = document.getElementById('paperExecutions');
  if (!data.paper_executions || data.paper_executions.length === 0) {
    root.innerHTML = '<div class="paper-execution">No paper execution records.</div>';
    return;
  }
  root.innerHTML = data.paper_executions.map(record => `<div class="paper-execution">
    <div class="grid">
      <div><div class="label">created_at</div><div class="value">${esc(record.created_at)}</div></div>
      <div><div class="label">paper_execution_id</div><div class="value mono">${esc(record.paper_execution_id)}</div></div>
      <div><div class="label">signal_id</div><div class="value mono">${esc(record.signal_id)}</div></div>
      <div><div class="label">direction/timeframe</div><div class="value">${esc(record.direction)}/${esc(record.timeframe)}</div></div>
      <div><div class="label">position_usd</div><div class="value">${esc(record.position_usd)}</div></div>
      <div><div class="label">leverage</div><div class="value">${esc(record.leverage)}</div></div>
      <div><div class="label">status</div><div class="value">${esc(record.status)}</div></div>
      <div><div class="label">paper_order_placed</div><div class="value safe">${esc(record.paper_order_placed)}</div></div>
      <div><div class="label">order_placed</div><div class="value danger">${esc(record.order_placed)}</div></div>
    </div>
  </div>`).join('');
}

async function recordDecision(index, decision) {
  const candidate = currentCandidates[index];
  if (!candidate) return;
  const signalId = candidate.signal_id;
  const notesInput = document.getElementById(`notes-${index}`);
  const operatorInput = document.getElementById('operator');
  const body = {
    signal_id: signalId,
    decision,
    operator: operatorInput ? operatorInput.value || 'josue' : 'josue',
    notes: notesInput ? notesInput.value : '',
    intended_position_usd: decision === 'approve_manual_live' ? 44 : 0,
    intended_leverage: decision === 'approve_manual_live' ? 2 : 0
  };
  const res = await fetch('/decisions', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body)
  });
  const data = await res.json();
  const message = document.getElementById('message');
  document.getElementById('order').textContent = String(data.order_placed === true);
  if (!res.ok) {
    message.className = 'feedback error';
    message.innerHTML = `<strong>API error ${res.status}</strong><pre>${esc(JSON.stringify(data, null, 2))}</pre>`;
  } else {
    message.className = 'feedback success';
    message.innerHTML = `<strong>Decision recorded:</strong> ${esc(data.decision)} | signal_id=${esc(data.signal_id)} | order_placed=${esc(data.order_placed)}`;
  }
  await loadDecisions();
}

async function loadDecisions() {
  const res = await fetch('/decisions?limit=10');
  const data = await res.json();
  const root = document.getElementById('decisions');
  if (!data.decisions || data.decisions.length === 0) {
    root.innerHTML = '<div class="decision">No decisions logged.</div>';
    return;
  }
  root.innerHTML = data.decisions.map(d => `<div class="decision">
    <div class="grid">
      <div><div class="label">created_at</div><div class="value">${esc(d.created_at)}</div></div>
      <div><div class="label">signal_id</div><div class="value mono">${esc(d.signal_id)}</div></div>
      <div><div class="label">decision</div><div class="value">${esc(d.decision)}</div></div>
      <div><div class="label">operator</div><div class="value">${esc(d.operator)}</div></div>
      <div><div class="label">order_placed</div><div class="value danger">${esc(d.order_placed)}</div></div>
      <div><div class="label">live_execution_enabled</div><div class="value danger">${esc(d.live_execution_enabled)}</div></div>
    </div>
    <div>${esc(d.notes)}</div>
  </div>`).join('');
}

refreshAll();
['latestOnly', 'eligibleOnly', 'includeForbidden', 'allowShort', 'limit'].forEach(id => {
  document.addEventListener('change', event => {
    if (event.target && event.target.id === id) {
      loadTradeTicket();
      loadExchangeDryRun();
      loadLiveSafety();
      loadCandidates();
    }
  });
});
setInterval(refreshAll, 30000);
</script>
</body>
</html>"""


def main() -> int:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8015)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
