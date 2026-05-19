"""Paper-only refresh scheduler for Hammer Radar.

R35 orchestrates the paper/watch intelligence stack. It never places orders,
creates ETH/alt live tickets, or changes BTCUSDT-only live readiness.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.betrayal_candle_archive import build_betrayal_candle_archive
from src.app.hammer_radar.operator.betrayal_candle_capture import backfill_betrayal_candle_capture
from src.app.hammer_radar.operator.betrayal_shadow_outcomes import track_betrayal_shadow_outcomes
from src.app.hammer_radar.operator.betrayal_shadow_resolver import resolve_betrayal_shadow_outcomes
from src.app.hammer_radar.operator.eth_paper_candidates import build_eth_paper_candidate
from src.app.hammer_radar.operator.eth_paper_outcomes import build_eth_paper_outcome
from src.app.hammer_radar.operator.final_human_review_packet import build_final_human_review_packet
from src.app.hammer_radar.operator.human_confirmation_records import build_human_confirmation_records
from src.app.hammer_radar.operator.review_record_aggregator import build_review_record_arming_snapshot
from src.app.hammer_radar.operator.source_warning_review import build_source_warning_review
from src.app.hammer_radar.operator.source_chain_repair import build_source_chain_repair
from src.app.hammer_radar.operator.candidate_revalidation_watch import build_candidate_revalidation_watch
from src.app.hammer_radar.operator.markov_regime_gate import build_markov_regime_gate
from src.app.hammer_radar.operator.market_intelligence import build_market_intelligence_summary
from src.app.hammer_radar.operator.miro_fish_quality_gate import build_miro_fish_quality_gate
from src.app.hammer_radar.operator.live_arming_preflight import build_live_arming_preflight
from src.app.hammer_radar.operator.live_env_arming_checklist import build_live_env_arming_checklist
from src.app.hammer_radar.operator.live_env_boundary_review import build_live_env_boundary_review
from src.app.hammer_radar.operator.multi_symbol_scanner import scan_watchlist
from src.app.hammer_radar.operator.notification_watcher import check_notifications, notification_status
from src.app.hammer_radar.operator.tiny_live_risk_contract import build_tiny_live_risk_contract_payload
from src.app.hammer_radar.operator.tiny_live_ticket_builder import build_tiny_live_ticket

LIVE_EXECUTION_ENABLED = False
ORDER_PLACED = False
SOURCE = "paper_refresh_scheduler"
RUNS_FILENAME = "paper_refresh_runs.ndjson"
WARNING = "Paper/watch refresh only. No live orders. No ETH/alt live tickets. BTCUSDT remains the only live-readiness symbol."
SERVICE_NAME = "hammer-paper-refresh.service"
SUGGESTED_SYSTEMD_UNIT_PATH = "ops/systemd/hammer-paper-refresh.service"
WATCHER_ENTRYPOINT = ".venv/bin/python -m src.app.hammer_radar.operator.paper_refresh_scheduler --watch"

TASK_MARKET_INTELLIGENCE = "market_intelligence"
TASK_MULTI_SYMBOL_SCAN = "multi_symbol_scan"
TASK_ETH_PAPER_CANDIDATE = "eth_paper_candidate"
TASK_ETH_PAPER_OUTCOME = "eth_paper_outcome"
TASK_BETRAYAL_SHADOW_TRACK = "betrayal_shadow_track"
TASK_BETRAYAL_SHADOW_RESOLVE = "betrayal_shadow_resolve"
TASK_BETRAYAL_CANDLE_ARCHIVE = "betrayal_candle_archive"
TASK_BETRAYAL_CANDLE_CAPTURE = "betrayal_candle_capture"
TASK_MARKOV_REGIME_GATE = "markov_regime_gate"
TASK_MIRO_FISH_QUALITY_GATE = "miro_fish_quality_gate"
TASK_LIVE_ARMING_PREFLIGHT = "live_arming_preflight"
TASK_TINY_LIVE_RISK_CONTRACT = "tiny_live_risk_contract"
TASK_TINY_LIVE_TICKET_BUILDER = "tiny_live_ticket_builder"
TASK_LIVE_ENV_ARMING_CHECKLIST = "live_env_arming_checklist"
TASK_LIVE_ENV_BOUNDARY_REVIEW = "live_env_boundary_review"
TASK_FINAL_HUMAN_REVIEW_PACKET = "final_human_review_packet"
TASK_HUMAN_CONFIRMATION_RECORDS = "human_confirmation_records"
TASK_REVIEW_RECORD_AGGREGATOR = "review_record_aggregator"
TASK_SOURCE_WARNING_REVIEW = "source_warning_review"
TASK_SOURCE_CHAIN_REPAIR = "source_chain_repair"
TASK_CANDIDATE_REVALIDATION_WATCH = "candidate_revalidation_watch"
TASK_NOTIFICATION_CHECK = "notification_check"

DEFAULT_TASKS = [
    TASK_MARKET_INTELLIGENCE,
    TASK_MULTI_SYMBOL_SCAN,
    TASK_ETH_PAPER_CANDIDATE,
    TASK_ETH_PAPER_OUTCOME,
    TASK_BETRAYAL_SHADOW_TRACK,
    TASK_NOTIFICATION_CHECK,
]
AVAILABLE_TASKS = (
    *DEFAULT_TASKS,
    TASK_BETRAYAL_SHADOW_RESOLVE,
    TASK_BETRAYAL_CANDLE_ARCHIVE,
    TASK_BETRAYAL_CANDLE_CAPTURE,
    TASK_MARKOV_REGIME_GATE,
    TASK_MIRO_FISH_QUALITY_GATE,
    TASK_LIVE_ARMING_PREFLIGHT,
    TASK_TINY_LIVE_RISK_CONTRACT,
    TASK_TINY_LIVE_TICKET_BUILDER,
    TASK_LIVE_ENV_ARMING_CHECKLIST,
    TASK_LIVE_ENV_BOUNDARY_REVIEW,
    TASK_FINAL_HUMAN_REVIEW_PACKET,
    TASK_HUMAN_CONFIRMATION_RECORDS,
    TASK_REVIEW_RECORD_AGGREGATOR,
    TASK_SOURCE_WARNING_REVIEW,
    TASK_SOURCE_CHAIN_REPAIR,
    TASK_CANDIDATE_REVALIDATION_WATCH,
)


@dataclass(frozen=True)
class PaperRefreshConfig:
    poll_seconds: int = 300
    use_network: bool = False
    write_outputs: bool = True
    send_notifications: bool = True
    tasks: tuple[str, ...] = tuple(DEFAULT_TASKS)
    max_errors: int = 5


def load_refresh_config() -> PaperRefreshConfig:
    return PaperRefreshConfig(
        poll_seconds=max(1, _int_env("HAMMER_REFRESH_POLL_SECONDS", 300)),
        use_network=_bool_env("HAMMER_REFRESH_USE_NETWORK", False),
        write_outputs=_bool_env("HAMMER_REFRESH_WRITE_OUTPUTS", True),
        send_notifications=_bool_env("HAMMER_REFRESH_SEND_NOTIFICATIONS", True),
        tasks=tuple(_parse_tasks(os.environ.get("HAMMER_REFRESH_TASKS"))),
        max_errors=max(1, _int_env("HAMMER_REFRESH_MAX_ERRORS", 5)),
    )


def scheduler_status(
    *,
    log_dir: str | Path | None = None,
    config: PaperRefreshConfig | None = None,
) -> dict[str, Any]:
    config = config or load_refresh_config()
    runs = load_refresh_runs(limit=0, log_dir=log_dir)
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "configured_poll_seconds": config.poll_seconds,
        "default_use_network": config.use_network,
        "default_write_outputs": config.write_outputs,
        "default_send_notifications": config.send_notifications,
        "available_tasks": list(AVAILABLE_TASKS),
        "configured_tasks": list(config.tasks),
        "runs_recorded": len(runs),
        "last_run": runs[0] if runs else None,
        "btc_live_only": True,
        "service_name": SERVICE_NAME,
        "suggested_systemd_unit_path": SUGGESTED_SYSTEMD_UNIT_PATH,
        "watcher_entrypoint": WATCHER_ENTRYPOINT,
        "warning": WARNING,
    }


def run_refresh_sequence(
    *,
    tasks: list[str] | tuple[str, ...] | None = None,
    use_network: bool | None = None,
    write_outputs: bool | None = None,
    send_notifications: bool | None = None,
    run_mode: str = "API",
    log_dir: str | Path | None = None,
    config: PaperRefreshConfig | None = None,
) -> dict[str, Any]:
    config = config or load_refresh_config()
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    requested_tasks = _validated_tasks(tasks if tasks is not None else config.tasks)
    effective_use_network = config.use_network if use_network is None else bool(use_network)
    effective_write_outputs = config.write_outputs if write_outputs is None else bool(write_outputs)
    effective_send_notifications = config.send_notifications if send_notifications is None else bool(send_notifications)
    started = time.monotonic()
    created_at = datetime.now(UTC).isoformat()
    completed_tasks: list[str] = []
    skipped_tasks: list[str] = []
    failed_tasks: list[str] = []
    task_results: dict[str, Any] = {}

    for task in requested_tasks:
        try:
            result = run_refresh_task(
                task,
                use_network=effective_use_network,
                write_outputs=effective_write_outputs,
                send_notifications=effective_send_notifications,
                log_dir=resolved_log_dir,
            )
            task_results[task] = result
            if result.get("skipped") is True:
                skipped_tasks.append(task)
            else:
                completed_tasks.append(task)
        except Exception as exc:  # pragma: no cover - defensive for watch loop/runtime.
            failed_tasks.append(task)
            task_results[task] = {
                "task": task,
                "status": "failed",
                "error_type": exc.__class__.__name__,
                "error": str(exc),
                "live_execution_enabled": LIVE_EXECUTION_ENABLED,
                "order_placed": ORDER_PLACED,
            }

    duration_ms = int((time.monotonic() - started) * 1000)
    run_record = {
        "refresh_run_id": _refresh_run_id(created_at=created_at),
        "created_at": created_at,
        "source": SOURCE,
        "run_mode": run_mode,
        "requested_tasks": requested_tasks,
        "completed_tasks": completed_tasks,
        "skipped_tasks": skipped_tasks,
        "failed_tasks": failed_tasks,
        "task_results": task_results,
        "duration_ms": duration_ms,
        "use_network": effective_use_network,
        "write_outputs": effective_write_outputs,
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "btc_live_only": True,
        "warning": WARNING,
        "send_notifications": effective_send_notifications,
    }
    append_refresh_run(run_record, log_dir=resolved_log_dir)
    return run_record


def run_refresh_task(
    task: str,
    *,
    use_network: bool,
    write_outputs: bool,
    send_notifications: bool,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    if task == TASK_MARKET_INTELLIGENCE:
        result = build_market_intelligence_summary(
            use_network=use_network,
            write=write_outputs,
            limit=20,
            log_dir=log_dir,
        )
        return _task_result(
            task,
            status="completed",
            detail={
                "market_data_status": result.get("market_data_status"),
                "network_used": result.get("network_used"),
                "symbols_count": result.get("symbols_count"),
                "write": result.get("write"),
            },
        )
    if task == TASK_MULTI_SYMBOL_SCAN:
        result = scan_watchlist(limit=50, write=write_outputs, log_dir=log_dir)
        return _task_result(
            task,
            status="completed",
            detail={
                "scanned_symbols": result.get("scanned_symbols"),
                "write": result.get("write"),
                "btc_live_only": result.get("btc_live_only"),
            },
        )
    if task == TASK_ETH_PAPER_CANDIDATE:
        result = build_eth_paper_candidate(use_network=use_network, write=write_outputs, log_dir=log_dir)
        return _task_result(
            task,
            status="completed",
            detail={
                "symbol": result.get("symbol"),
                "paper_candidate_status": result.get("paper_candidate_status"),
                "tier": result.get("tier"),
                "write": result.get("write"),
            },
        )
    if task == TASK_ETH_PAPER_OUTCOME:
        result = build_eth_paper_outcome(write=write_outputs, log_dir=log_dir)
        return _task_result(
            task,
            status="completed",
            detail={
                "symbol": result.get("symbol"),
                "outcome_status": result.get("outcome_status"),
                "outcome_created": result.get("outcome_created"),
                "write": result.get("write"),
            },
        )
    if task == TASK_BETRAYAL_SHADOW_TRACK:
        if not write_outputs:
            return _task_result(task, status="skipped", skipped=True, detail={"reason": "write_outputs=false"})
        result = track_betrayal_shadow_outcomes(latest_only=True, limit=20, since_hours=24, log_dir=log_dir)
        return _task_result(
            task,
            status="completed",
            detail={
                "created": result.get("created"),
                "updated": result.get("updated"),
                "candidate_count": result.get("candidate_count"),
                "shadow_only": result.get("shadow_only"),
            },
        )
    if task == TASK_BETRAYAL_SHADOW_RESOLVE:
        result = resolve_betrayal_shadow_outcomes(
            limit=50,
            since_hours=24,
            dry_run=True,
            write=False,
            log_dir=log_dir,
        )
        return _task_result(
            task,
            status="completed",
            detail={
                "scanned_records": result.get("scanned_records"),
                "newly_resolved_records": result.get("newly_resolved_records"),
                "dry_run": result.get("dry_run"),
                "write": result.get("write"),
            },
        )
    if task == TASK_BETRAYAL_CANDLE_ARCHIVE:
        result = build_betrayal_candle_archive(
            limit=100,
            since_hours=24,
            dry_run=True,
            write=False,
            log_dir=log_dir,
        )
        return _task_result(
            task,
            status="completed",
            detail={
                "candles_found": result.get("candles_found"),
                "candles_written": result.get("candles_written"),
                "dry_run": result.get("dry_run"),
                "write": result.get("write"),
            },
        )
    if task == TASK_BETRAYAL_CANDLE_CAPTURE:
        result = backfill_betrayal_candle_capture(
            limit=100,
            since_hours=24,
            dry_run=True,
            write=False,
            log_dir=log_dir,
        )
        return _task_result(
            task,
            status="completed",
            detail={
                "candles_found": result.get("candles_found"),
                "candles_written": result.get("candles_written"),
                "source_mode": result.get("source_mode"),
                "dry_run": result.get("dry_run"),
                "write": result.get("write"),
            },
        )
    if task == TASK_MARKOV_REGIME_GATE:
        result = build_markov_regime_gate(limit=120, log_dir=log_dir)
        return _task_result(
            task,
            status="completed",
            detail={
                "normal_candidate_gates": len(result.get("normal_candidate_regime_gates") or []),
                "betrayal_candidate_gates": len(result.get("betrayal_candidate_regime_gates") or []),
                "regime_timeframes": len(result.get("regime_summary") or {}),
                "execution_mode": result.get("execution_mode"),
            },
        )
    if task == TASK_MIRO_FISH_QUALITY_GATE:
        result = build_miro_fish_quality_gate(limit=120, log_dir=log_dir)
        return _task_result(
            task,
            status="completed",
            detail={
                "normal_candidate_gates": len(result.get("normal_candidate_quality_gates") or []),
                "betrayal_candidate_gates": len(result.get("betrayal_candidate_quality_gates") or []),
                "supported_candidates": len(result.get("top_supported_candidates") or []),
                "execution_mode": result.get("execution_mode"),
            },
        )
    if task == TASK_LIVE_ARMING_PREFLIGHT:
        result = build_live_arming_preflight(log_dir=log_dir)
        return _task_result(
            task,
            status="completed",
            detail={
                "final_preflight_status": result.get("final_preflight_status"),
                "selected_candidate_id": (result.get("top_candidate_preflight") or {}).get("candidate_id"),
                "execution_mode": result.get("execution_mode"),
            },
        )
    if task == TASK_TINY_LIVE_RISK_CONTRACT:
        result = build_tiny_live_risk_contract_payload()
        return _task_result(
            task,
            status="completed",
            detail={
                "candidate_id": result.get("candidate_id"),
                "validation_status": (result.get("validation") or {}).get("validation_status"),
                "execution_mode": result.get("execution_mode"),
            },
        )
    if task == TASK_TINY_LIVE_TICKET_BUILDER:
        result = build_tiny_live_ticket(dry_run=True, write=False, log_dir=log_dir)
        return _task_result(
            task,
            status="completed",
            detail={
                "candidate_id": result.get("candidate_id"),
                "ticket_status": result.get("ticket_status"),
                "approval_status": result.get("operator_approval_status"),
                "ticket_written": result.get("ticket_written"),
                "execution_mode": result.get("execution_mode"),
            },
        )
    if task == TASK_LIVE_ENV_ARMING_CHECKLIST:
        result = build_live_env_arming_checklist(dry_run=True, write=False, log_dir=log_dir)
        return _task_result(
            task,
            status="completed",
            detail={
                "candidate_id": result.get("candidate_id"),
                "checklist_status": result.get("checklist_status"),
                "manual_funding_status": result.get("manual_funding_status"),
                "live_env_arming_status": result.get("live_env_arming_status"),
                "checklist_written": result.get("checklist_written"),
                "execution_mode": result.get("execution_mode"),
            },
        )
    if task == TASK_LIVE_ENV_BOUNDARY_REVIEW:
        result = build_live_env_boundary_review(dry_run=True, write=False, log_dir=log_dir)
        return _task_result(
            task,
            status="completed",
            detail={
                "candidate_id": result.get("candidate_id"),
                "boundary_status": result.get("boundary_status"),
                "source_preflight_status": result.get("source_preflight_status"),
                "report_written": result.get("report_written"),
                "execution_mode": result.get("execution_mode"),
            },
        )
    if task == TASK_FINAL_HUMAN_REVIEW_PACKET:
        result = build_final_human_review_packet(dry_run=True, write=False, log_dir=log_dir)
        return _task_result(
            task,
            status="completed",
            detail={
                "candidate_id": result.get("candidate_id"),
                "packet_status": result.get("packet_status"),
                "final_human_approval_status": result.get("final_human_approval_status"),
                "packet_written": result.get("packet_written"),
                "execution_mode": result.get("execution_mode"),
            },
        )
    if task == TASK_HUMAN_CONFIRMATION_RECORDS:
        result = build_human_confirmation_records(dry_run=True, write=False, log_dir=log_dir)
        return _task_result(
            task,
            status="completed",
            detail={
                "candidate_id": result.get("candidate_id"),
                "unified_readiness_status": result.get("unified_readiness_status"),
                "records_written": result.get("records_written"),
                "r87_boundary_status": result.get("r87_boundary_status"),
                "execution_mode": result.get("execution_mode"),
            },
        )
    if task == TASK_REVIEW_RECORD_AGGREGATOR:
        result = build_review_record_arming_snapshot(dry_run=True, write=False, log_dir=log_dir)
        return _task_result(
            task,
            status="completed",
            detail={
                "candidate_id": result.get("candidate_id"),
                "snapshot_status": result.get("snapshot_status"),
                "readiness_class": result.get("readiness_class"),
                "hash_chain_consistent": (result.get("hash_chain_summary") or {}).get("hash_chain_consistent"),
                "snapshot_written": result.get("snapshot_written"),
                "execution_mode": result.get("execution_mode"),
            },
        )
    if task == TASK_SOURCE_WARNING_REVIEW:
        result = build_source_warning_review(dry_run=True, write=False, log_dir=log_dir)
        return _task_result(
            task,
            status="completed",
            detail={
                "candidate_id": result.get("candidate_id"),
                "source_warning_classification": result.get("source_warning_classification"),
                "rehydration_status": (result.get("rehydrated_review_context") or {}).get("rehydration_status"),
                "report_written": result.get("report_written"),
                "execution_mode": result.get("execution_mode"),
            },
        )
    if task == TASK_SOURCE_CHAIN_REPAIR:
        result = build_source_chain_repair(dry_run=True, write=False, log_dir=log_dir)
        return _task_result(
            task,
            status="completed",
            detail={
                "candidate_id": result.get("candidate_id"),
                "repair_classification": result.get("repair_classification"),
                "recommended_next_phase": result.get("recommended_next_phase"),
                "report_written": result.get("report_written"),
                "execution_mode": result.get("execution_mode"),
            },
        )
    if task == TASK_CANDIDATE_REVALIDATION_WATCH:
        result = build_candidate_revalidation_watch(dry_run=True, write=False, log_dir=log_dir)
        return _task_result(
            task,
            status="completed",
            detail={
                "candidate_id": result.get("candidate_id"),
                "revalidation_class": result.get("revalidation_class"),
                "support_restored": result.get("support_restored"),
                "next_action_recommendation": result.get("next_action_recommendation"),
                "report_written": result.get("report_written"),
                "execution_mode": result.get("execution_mode"),
            },
        )
    if task == TASK_NOTIFICATION_CHECK:
        result = check_notifications(
            send=send_notifications,
            channel="telegram" if send_notifications else "none",
            log_dir=log_dir,
        )
        return _task_result(
            task,
            status="completed",
            detail={
                "send_requested": result.get("send_requested"),
                "would_alert": result.get("would_alert"),
                "recorded": result.get("recorded"),
                "telegram": result.get("telegram"),
                "secrets_shown": result.get("secrets_shown"),
            },
        )
    raise ValueError(f"unsupported refresh task: {task}")


def load_refresh_runs(*, limit: int = 50, log_dir: str | Path | None = None) -> list[dict[str, Any]]:
    path = _runs_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    records = list(reversed(records))
    if limit > 0:
        return records[:limit]
    return records


def append_refresh_run(record: dict[str, Any], *, log_dir: str | Path | None = None) -> None:
    path = _runs_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def build_refresh_runs_payload(*, limit: int = 50, log_dir: str | Path | None = None) -> dict[str, Any]:
    records = load_refresh_runs(limit=limit, log_dir=log_dir)
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "btc_live_only": True,
        "runs": records,
        "runs_recorded": len(load_refresh_runs(limit=0, log_dir=log_dir)),
        "warning": WARNING,
    }


def build_refresh_status_text(*, log_dir: str | Path | None = None) -> str:
    status = scheduler_status(log_dir=log_dir)
    return "\n".join(
        [
            "HAMMER RADAR PAPER REFRESH STATUS",
            "live_execution_enabled: false",
            "order_placed: false",
            "btc_live_only: true",
            f"configured_poll_seconds: {status['configured_poll_seconds']}",
            f"default_use_network: {str(status['default_use_network']).lower()}",
            f"default_write_outputs: {str(status['default_write_outputs']).lower()}",
            f"default_send_notifications: {str(status['default_send_notifications']).lower()}",
            f"available_tasks: {', '.join(status['available_tasks'])}",
            f"runs_recorded: {status['runs_recorded']}",
        ]
    )


def build_refresh_run_text(
    *,
    tasks: str | None = None,
    use_network: bool = False,
    write_outputs: bool = True,
    send_notifications: bool = False,
    log_dir: str | Path | None = None,
) -> str:
    selected_tasks = _parse_tasks(tasks) if tasks else None
    record = run_refresh_sequence(
        tasks=selected_tasks,
        use_network=use_network,
        write_outputs=write_outputs,
        send_notifications=send_notifications,
        run_mode="CLI",
        log_dir=log_dir,
    )
    return "\n".join(
        [
            "HAMMER RADAR PAPER REFRESH RUN",
            "live_execution_enabled: false",
            "order_placed: false",
            "btc_live_only: true",
            f"refresh_run_id: {record['refresh_run_id']}",
            f"completed_tasks: {', '.join(record['completed_tasks']) if record['completed_tasks'] else 'none'}",
            f"skipped_tasks: {', '.join(record['skipped_tasks']) if record['skipped_tasks'] else 'none'}",
            f"failed_tasks: {', '.join(record['failed_tasks']) if record['failed_tasks'] else 'none'}",
            f"use_network: {str(record['use_network']).lower()}",
            f"write_outputs: {str(record['write_outputs']).lower()}",
            f"send_notifications: {str(record['send_notifications']).lower()}",
        ]
    )


def build_refresh_runs_text(*, limit: int = 50, log_dir: str | Path | None = None) -> str:
    payload = build_refresh_runs_payload(limit=limit, log_dir=log_dir)
    lines = [
        "HAMMER RADAR PAPER REFRESH RUNS",
        "live_execution_enabled: false",
        "order_placed: false",
        "btc_live_only: true",
        f"records: {len(payload['runs'])}",
    ]
    if not payload["runs"]:
        return "\n".join([*lines, "no paper refresh runs"])
    for record in payload["runs"]:
        lines.append(
            f"{record.get('created_at')} | {record.get('refresh_run_id')} | "
            f"completed={len(record.get('completed_tasks') or [])} | "
            f"failed={len(record.get('failed_tasks') or [])} | duration_ms={record.get('duration_ms')}"
        )
    return "\n".join(lines)


def watch_loop(*, log_dir: str | Path | None = None, config: PaperRefreshConfig | None = None) -> None:
    config = config or load_refresh_config()
    consecutive_errors = 0
    while True:
        try:
            record = run_refresh_sequence(
                tasks=list(config.tasks),
                use_network=config.use_network,
                write_outputs=config.write_outputs,
                send_notifications=config.send_notifications,
                run_mode="WATCH_LOOP",
                log_dir=log_dir,
                config=config,
            )
            consecutive_errors = 0 if not record["failed_tasks"] else consecutive_errors + 1
            print(
                "paper_refresh "
                f"run_id={record['refresh_run_id']} completed={len(record['completed_tasks'])} "
                f"failed={len(record['failed_tasks'])} order_placed=false"
            )
        except Exception as exc:  # pragma: no cover - defensive watcher behavior.
            consecutive_errors += 1
            print(f"paper_refresh error={exc.__class__.__name__} order_placed=false")
        if consecutive_errors >= config.max_errors:
            print("paper_refresh stopping=max_errors order_placed=false")
            return
        time.sleep(config.poll_seconds)


def _task_result(
    task: str,
    *,
    status: str,
    detail: dict[str, Any],
    skipped: bool = False,
) -> dict[str, Any]:
    return {
        "task": task,
        "status": status,
        "skipped": bool(skipped),
        "detail": detail,
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
    }


def _parse_tasks(raw: str | None) -> list[str]:
    if raw is None or not raw.strip():
        return list(DEFAULT_TASKS)
    return _validated_tasks([part.strip() for part in raw.split(",") if part.strip()])


def _validated_tasks(tasks: list[str] | tuple[str, ...]) -> list[str]:
    unknown = [task for task in tasks if task not in AVAILABLE_TASKS]
    if unknown:
        raise ValueError(f"unsupported refresh task(s): {', '.join(unknown)}")
    return list(tasks)


def _bool_env(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _refresh_run_id(*, created_at: str) -> str:
    digest = hashlib.sha256(f"{SOURCE}|{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"prefresh_{digest}"


def _runs_path(log_dir: Path) -> Path:
    return log_dir / RUNS_FILENAME


def _main() -> int:
    parser = argparse.ArgumentParser(prog="python -m src.app.hammer_radar.operator.paper_refresh_scheduler")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--log-dir", default=None)
    args = parser.parse_args()
    if args.watch:
        watch_loop(log_dir=args.log_dir)
        return 0
    print(build_refresh_run_text(log_dir=args.log_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
