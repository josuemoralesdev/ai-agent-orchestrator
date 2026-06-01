"""R160 fundless short dry-run packet and operator arming checklist.

This module is packet/checklist only. It composes existing R159/R158/R156/R157
read-only surfaces for the BTCUSDT 8m short lane and never creates executable
order payloads, protective payloads, signed requests, Binance calls, config
writes, env writes, lane-mode changes, or live-execution authority.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.fundless_short_tiny_live_readiness_rehearsal import (
    RISK_CONTRACT_CONFIG_PATH,
    build_funding_gate_summary,
    build_fundless_short_tiny_live_readiness_rehearsal,
    build_short_risk_contract_preview,
)
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.short_evidence_recheck_packet import (
    DEFAULT_LATEST_BETRAYAL_RECHECK,
    DEFAULT_LATEST_CAPTURES,
    PROMOTION_PACKET_READY_FOR_OPERATOR_REVIEW,
)
from src.app.hammer_radar.operator.short_paper_evidence_capture_loop import CONFIRM_SHORT_PAPER_CAPTURE_PHRASE
from src.app.hammer_radar.operator.short_strategy_packet import (
    DEFAULT_LATEST_OUTCOMES,
    DEFAULT_LATEST_SIGNALS,
    DEFAULT_TARGET_LANE_KEY,
    MIN_FRESH_CANDIDATES,
    build_short_golden_pocket_interpretation,
    build_short_strategy_target_family,
)

FUNDLESS_SHORT_DRY_RUN_PACKET_READY = "FUNDLESS_SHORT_DRY_RUN_PACKET_READY"
FUNDLESS_SHORT_DRY_RUN_PACKET_REJECTED = "FUNDLESS_SHORT_DRY_RUN_PACKET_REJECTED"
FUNDLESS_SHORT_DRY_RUN_PACKET_RECORDED = "FUNDLESS_SHORT_DRY_RUN_PACKET_RECORDED"
FUNDLESS_SHORT_DRY_RUN_PACKET_BLOCKED = "FUNDLESS_SHORT_DRY_RUN_PACKET_BLOCKED"
FUNDLESS_SHORT_DRY_RUN_PACKET_ERROR = "FUNDLESS_SHORT_DRY_RUN_PACKET_ERROR"

PACKET_READY_BUT_EXECUTION_BLOCKED = "PACKET_READY_BUT_EXECUTION_BLOCKED"
NOT_READY_EVIDENCE_BLOCKED = "NOT_READY_EVIDENCE_BLOCKED"
NOT_READY_FUNDING_BLOCKED = "NOT_READY_FUNDING_BLOCKED"
NOT_READY_RISK_CONTRACT_BLOCKED = "NOT_READY_RISK_CONTRACT_BLOCKED"
NOT_READY_PROTECTIVE_POLICY_BLOCKED = "NOT_READY_PROTECTIVE_POLICY_BLOCKED"
NOT_READY_MULTIPLE_BLOCKERS = "NOT_READY_MULTIPLE_BLOCKERS"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

KEEP_R157_RUNNING = "KEEP_R157_RUNNING"
RUN_R158_RECHECK_AFTER_MORE_CAPTURES = "RUN_R158_RECHECK_AFTER_MORE_CAPTURES"
FUND_ACCOUNT_LATER = "FUND_ACCOUNT_LATER"
RUN_R161_RISK_CONTRACT_DRAFT_PREVIEW = "RUN_R161_RISK_CONTRACT_DRAFT_PREVIEW"

EVENT_TYPE = "FUNDLESS_SHORT_DRY_RUN_PACKET"
LEDGER_FILENAME = "fundless_short_dry_run_packets.ndjson"
CONFIRM_FUNDLESS_SHORT_DRY_RUN_PACKET_RECORDING_PHRASE = (
    "I CONFIRM FUNDLESS SHORT DRY RUN PACKET RECORDING ONLY; NO LANE CHANGES; NO ORDER; NO BINANCE CALL."
)

DEFAULT_LATEST_BETRAYAL = DEFAULT_LATEST_BETRAYAL_RECHECK

SAFETY = {
    **SAFETY_FALSE,
    "real_order_placed": False,
    "order_payload_created": False,
    "executable_payload_created": False,
    "protective_payload_created": False,
    "signed_request_created": False,
    "network_allowed": False,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "protective_order_endpoint_called": False,
    "secrets_shown": False,
    "paper_live_separation_intact": True,
    "env_mutated": False,
    "config_written": False,
    "global_live_flags_changed": False,
}

SOURCE_SURFACES_USED = [
    "configs/hammer_radar/lane_controls.json",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
    "logs/hammer_radar_forward/fundless_short_tiny_live_readiness_rehearsals.ndjson",
    "logs/hammer_radar_forward/short_evidence_recheck_packets.ndjson",
    "logs/hammer_radar_forward/short_paper_evidence_capture.ndjson",
    "operator.fundless_short_tiny_live_readiness_rehearsal.build_fundless_short_tiny_live_readiness_rehearsal",
    "operator.short_evidence_recheck_packet.build_short_evidence_recheck_packet",
    "operator.short_strategy_packet.build_short_strategy_target_family",
    "operator.short_strategy_packet.build_short_golden_pocket_interpretation",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_fundless_short_dry_run_packet(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    latest_captures: int = DEFAULT_LATEST_CAPTURES,
    latest_outcomes: int = DEFAULT_LATEST_OUTCOMES,
    latest_signals: int = DEFAULT_LATEST_SIGNALS,
    latest_betrayal: int = DEFAULT_LATEST_BETRAYAL,
    record_packet: bool = False,
    confirm_fundless_short_dry_run: str | None = None,
    config_path: str | Path | None = None,
    risk_contract_config_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_fundless_short_dry_run == CONFIRM_FUNDLESS_SHORT_DRY_RUN_PACKET_RECORDING_PHRASE
    try:
        target = build_target_lane_snapshot(lane_key=lane_key, config_path=config_path)
        rehearsal = build_fundless_short_tiny_live_readiness_rehearsal(
            log_dir=resolved_log_dir,
            lane_key=target["lane_key"],
            latest_captures=latest_captures,
            latest_outcomes=latest_outcomes,
            latest_signals=latest_signals,
            latest_betrayal=latest_betrayal,
            record_rehearsal=False,
            config_path=config_path,
            risk_contract_config_path=risk_contract_config_path,
            now=generated_at,
        )
        risk_requirements = build_risk_contract_requirements(
            target_family=target,
            risk_contract_config_path=risk_contract_config_path,
        )
        protective_requirements = build_protective_policy_requirements(target_family=target)
        live_lockdown = build_live_flag_lockdown_summary()
        matrix = build_future_conditions_matrix(
            rehearsal=rehearsal,
            risk_contract_requirements=risk_requirements,
            protective_policy_requirements=protective_requirements,
            live_flag_lockdown=live_lockdown,
        )
        readiness = classify_dry_run_packet_readiness(matrix, target_family=target)
        blockers = _blockers(matrix=matrix, target_family=target, readiness=readiness)
        status = FUNDLESS_SHORT_DRY_RUN_PACKET_READY
        if readiness == UNKNOWN_NEEDS_MANUAL_REVIEW or target.get("current_mode") != "paper":
            status = FUNDLESS_SHORT_DRY_RUN_PACKET_BLOCKED
        if record_packet and not confirmation_valid:
            status = FUNDLESS_SHORT_DRY_RUN_PACKET_REJECTED
        elif record_packet and confirmation_valid:
            status = FUNDLESS_SHORT_DRY_RUN_PACKET_RECORDED

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "packet_recorded": False,
            "packet_id": None,
            "record_packet_requested": bool(record_packet),
            "confirmation_valid": bool(confirmation_valid),
            "target_family": target,
            "future_conditions_matrix": matrix,
            "non_executable_dry_run_fields": build_non_executable_dry_run_fields(target_family=target),
            "operator_arming_checklist": build_operator_arming_checklist(matrix=matrix, target_family=target),
            "funding_verification_plan": build_funding_verification_plan(),
            "risk_contract_requirements": risk_requirements,
            "protective_policy_requirements": protective_requirements,
            "live_flag_lockdown": live_lockdown,
            "readiness": readiness,
            "blockers": blockers,
            "recommended_next_operator_move": _recommended_next_operator_move(readiness, matrix=matrix),
            "recommended_next_engineering_move": _recommended_next_engineering_move(readiness),
            "safe_commands": _safe_commands(target["lane_key"]),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
            "source_rehearsal": {
                "status": rehearsal.get("status"),
                "readiness": rehearsal.get("readiness"),
                "rehearsal_recorded": bool(rehearsal.get("rehearsal_recorded")),
                "source_evidence_recheck": dict(rehearsal.get("source_evidence_recheck") or {}),
            },
        }
        if record_packet and confirmation_valid:
            record = append_fundless_short_dry_run_packet_record(payload, log_dir=resolved_log_dir)
            payload["packet_recorded"] = True
            payload["packet_id"] = record["packet_id"]
            payload["ledger_path"] = str(fundless_short_dry_run_packet_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        target = _target_from_key(lane_key, mode="unknown")
        return _sanitize(
            {
                "status": FUNDLESS_SHORT_DRY_RUN_PACKET_ERROR,
                "generated_at": generated_at.isoformat(),
                "packet_recorded": False,
                "packet_id": None,
                "record_packet_requested": bool(record_packet),
                "confirmation_valid": bool(confirmation_valid),
                "target_family": target,
                "future_conditions_matrix": build_future_conditions_matrix(),
                "non_executable_dry_run_fields": build_non_executable_dry_run_fields(target_family=target),
                "operator_arming_checklist": build_operator_arming_checklist(),
                "funding_verification_plan": build_funding_verification_plan(),
                "risk_contract_requirements": build_risk_contract_requirements(target_family=target),
                "protective_policy_requirements": build_protective_policy_requirements(target_family=target),
                "live_flag_lockdown": build_live_flag_lockdown_summary(),
                "readiness": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "blockers": ["R160 dry-run packet build error must be fixed before review"],
                "recommended_next_operator_move": RUN_R158_RECHECK_AFTER_MORE_CAPTURES,
                "recommended_next_engineering_move": "Fix the R160 dry-run packet builder error; do not mutate lane config.",
                "safe_commands": _safe_commands(lane_key),
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def build_target_lane_snapshot(
    *,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    return build_short_strategy_target_family(lane_key=lane_key, config_path=config_path)


def build_future_conditions_matrix(
    *,
    rehearsal: Mapping[str, Any] | None = None,
    risk_contract_requirements: Mapping[str, Any] | None = None,
    protective_policy_requirements: Mapping[str, Any] | None = None,
    live_flag_lockdown: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    source = dict(rehearsal or {})
    evidence = dict(source.get("evidence_gate") or {})
    funding = dict(source.get("funding_gate") or build_funding_gate_summary())
    source_evidence_recheck = dict(source.get("source_evidence_recheck") or {})
    promotion = dict(source_evidence_recheck.get("promotion_readiness") or {})
    risk = dict(risk_contract_requirements or build_risk_contract_requirements())
    protective = dict(protective_policy_requirements or build_protective_policy_requirements())
    live_flags = dict(live_flag_lockdown or build_live_flag_lockdown_summary())
    fresh_count = int(evidence.get("fresh_capture_count") or 0)
    required = int(evidence.get("required_fresh_capture_count") or MIN_FRESH_CANDIDATES)
    evidence_satisfied = (
        fresh_count >= required
        and evidence.get("fresh_evidence_threshold_met") is True
        and promotion.get("readiness") == PROMOTION_PACKET_READY_FOR_OPERATOR_REVIEW
    )
    return {
        "fresh_evidence": {
            "required": "fresh captures >= 10",
            "current": f"{fresh_count} / {required}",
            "satisfied": bool(evidence_satisfied),
        },
        "funding": {
            "required": "account balance verified and sufficient",
            "current": funding.get("funding_status") or "UNKNOWN_NOT_CHECKED",
            "satisfied": funding.get("funding_ready") is True,
        },
        "risk_contract": {
            "required": "8m short tiny-live risk contract reviewed",
            "current": "present" if risk.get("target_lane_has_contract") is True else "missing_for_target_lane",
            "satisfied": risk.get("target_lane_has_contract") is True,
        },
        "protective_policy": {
            "required": "short-specific stop/TP/protective policy reviewed",
            "current": "preview_only_not_reviewed",
            "satisfied": False,
        },
        "operator_approval": {
            "required": "explicit future approval phrase",
            "current": "not provided",
            "satisfied": False,
        },
        "global_live_flags": {
            "required": "intentionally armed in later phase only",
            "current": "disabled/locked",
            "satisfied": live_flags.get("live_execution_enabled") is True and live_flags.get("short_tiny_live_authorized") is True,
        },
    }


def build_non_executable_dry_run_fields(*, target_family: Mapping[str, Any] | None = None) -> dict[str, Any]:
    target = dict(target_family or _target_from_key(DEFAULT_TARGET_LANE_KEY, mode="paper"))
    return {
        "intent_type": "FUNDLESS_SHORT_TINY_LIVE_DRY_RUN_PACKET_ONLY",
        "symbol": target.get("symbol") or "BTCUSDT",
        "side": "SELL",
        "timeframe": target.get("timeframe") or "8m",
        "entry_mode": target.get("entry_mode") or "ladder_close_50_618",
        "notional_usdt": None,
        "quantity": None,
        "entry_price": None,
        "stop_price": None,
        "take_profit_price": None,
        "protective_orders_required": True,
        "would_build_order_payload": False,
        "would_submit_order": False,
        "would_call_binance": False,
        "executable": False,
    }


def build_operator_arming_checklist(
    *,
    matrix: Mapping[str, Any] | None = None,
    target_family: Mapping[str, Any] | None = None,
) -> dict[str, list[str]]:
    target = dict(target_family or {})
    conditions = dict(matrix or build_future_conditions_matrix())
    currently_true: list[str] = []
    currently_blocked: list[str] = []
    if target.get("current_mode") == "paper":
        currently_true.append("target short lane remains paper")
    else:
        currently_blocked.append("target short lane must remain paper")
    for key, label in [
        ("fresh_evidence", "fresh captures >= 10"),
        ("funding", "account balance verified and sufficient"),
        ("risk_contract", "8m short tiny-live risk contract reviewed"),
        ("protective_policy", "short-specific stop/TP/protective policy reviewed"),
        ("operator_approval", "explicit future approval phrase"),
        ("global_live_flags", "live flags intentionally armed in later phase"),
    ]:
        if dict(conditions.get(key) or {}).get("satisfied") is True:
            currently_true.append(label)
        else:
            currently_blocked.append(label)
    return {
        "must_be_true_before_future_live_discussion": [
            "target short lane remains paper until a future approved lane-mode phase",
            "fresh captures >= 10",
            "R158 promotion-readiness packet ready for operator review",
            "account balance verified and sufficient",
            "8m short tiny-live risk contract reviewed",
            "short-specific stop/TP/protective policy reviewed",
            "global kill switch and live flags intentionally reviewed in a later phase",
            "explicit future approval phrase",
        ],
        "currently_true": _dedupe(currently_true),
        "currently_blocked": _dedupe(currently_blocked),
        "explicit_forbidden_now": _do_not_run_yet(),
    }


def build_funding_verification_plan() -> dict[str, Any]:
    return {
        "safe_future_check": "binance-readonly-status / balance read-only if available",
        "requires_account_funded": True,
        "no_funding_action_taken": True,
        "no_network_required_for_this_packet": True,
    }


def build_risk_contract_requirements(
    *,
    target_family: Mapping[str, Any] | None = None,
    risk_contract_config_path: str | Path | None = None,
) -> dict[str, Any]:
    preview = build_short_risk_contract_preview(
        target_family=target_family or _target_from_key(DEFAULT_TARGET_LANE_KEY, mode="paper"),
        risk_contract_config_path=risk_contract_config_path or RISK_CONTRACT_CONFIG_PATH,
    )
    return {
        "must_exist_for_target_lane": True,
        "target_lane_has_contract": bool(preview.get("target_lane_has_contract")),
        "max_daily_trades": int(preview.get("max_daily_trades") or 1),
        "max_daily_loss_pct": _number_or_default(preview.get("max_daily_loss_pct"), 0.15),
        "requires_protective_orders": True,
        "short_specific_stop_tp_required": True,
        "contract_change_allowed_now": False,
    }


def build_protective_policy_requirements(*, target_family: Mapping[str, Any] | None = None) -> dict[str, Any]:
    interpretation = build_short_golden_pocket_interpretation(dict(target_family or {}))
    return {
        "golden_pocket_role": interpretation.get("golden_pocket_role") or "resistance/retrace zone",
        "invalidation_concept": "above relevant swing high/resistance",
        "take_profit_concept": "below entry toward downside continuation/liquidity",
        "protective_policy_change_allowed_now": False,
    }


def build_live_flag_lockdown_summary() -> dict[str, Any]:
    return {
        "live_execution_enabled": False,
        "global_kill_switch_authoritative": True,
        "short_tiny_live_authorized": False,
        "lane_mode_change_allowed_now": False,
    }


def classify_dry_run_packet_readiness(
    matrix: Mapping[str, Any] | None = None,
    *,
    target_family: Mapping[str, Any] | None = None,
) -> str:
    target = dict(target_family or {})
    if target and (target.get("direction") != "short" or target.get("current_mode") != "paper"):
        return UNKNOWN_NEEDS_MANUAL_REVIEW
    conditions = dict(matrix or {})
    blocker_keys = [
        key
        for key in ("fresh_evidence", "funding", "risk_contract", "protective_policy", "operator_approval", "global_live_flags")
        if dict(conditions.get(key) or {}).get("satisfied") is not True
    ]
    if not blocker_keys:
        return PACKET_READY_BUT_EXECUTION_BLOCKED
    if len(blocker_keys) > 1:
        return NOT_READY_MULTIPLE_BLOCKERS
    only = blocker_keys[0]
    return {
        "fresh_evidence": NOT_READY_EVIDENCE_BLOCKED,
        "funding": NOT_READY_FUNDING_BLOCKED,
        "risk_contract": NOT_READY_RISK_CONTRACT_BLOCKED,
        "protective_policy": NOT_READY_PROTECTIVE_POLICY_BLOCKED,
    }.get(only, UNKNOWN_NEEDS_MANUAL_REVIEW)


def append_fundless_short_dry_run_packet_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = fundless_short_dry_run_packet_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "packet_id": record.get("packet_id") or f"r160_fundless_short_dry_run_packet_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "record_packet_requested": bool(record.get("record_packet_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_family": dict(record.get("target_family") or {}),
            "future_conditions_matrix": dict(record.get("future_conditions_matrix") or {}),
            "non_executable_dry_run_fields": dict(record.get("non_executable_dry_run_fields") or {}),
            "operator_arming_checklist": dict(record.get("operator_arming_checklist") or {}),
            "funding_verification_plan": dict(record.get("funding_verification_plan") or {}),
            "risk_contract_requirements": dict(record.get("risk_contract_requirements") or {}),
            "protective_policy_requirements": dict(record.get("protective_policy_requirements") or {}),
            "live_flag_lockdown": dict(record.get("live_flag_lockdown") or {}),
            "readiness": record.get("readiness"),
            "blockers": list(record.get("blockers") or []),
            "recommended_next_operator_move": record.get("recommended_next_operator_move"),
            "recommended_next_engineering_move": record.get("recommended_next_engineering_move"),
            "safe_commands": list(record.get("safe_commands") or []),
            "do_not_run_yet": list(record.get("do_not_run_yet") or []),
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_fundless_short_dry_run_packet_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = fundless_short_dry_run_packet_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        records = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    records.append(_sanitize(json.loads(line)))
        return records
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=32_000_000)]


def summarize_fundless_short_dry_run_packets(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    readiness_counts = Counter(str(record.get("readiness") or "UNKNOWN") for record in records)
    latest = records[0] if records else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "readiness_counts": dict(sorted(readiness_counts.items())),
        "last_packet_id": latest.get("packet_id"),
        "last_target_lane": (latest.get("target_family") or {}).get("lane_key") if isinstance(latest.get("target_family"), Mapping) else None,
        "safety": dict(SAFETY),
    }


def fundless_short_dry_run_packet_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_fundless_short_dry_run_packet_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _safe_commands(lane_key: str) -> list[str]:
    return [
        _r157_capture_command(lane_key),
        _r158_recheck_command(lane_key),
        _r159_rehearsal_command(lane_key),
        _record_command(lane_key),
    ]


def _r157_capture_command(lane_key: str) -> str:
    return (
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
        "--log-dir logs/hammer_radar_forward short-paper-evidence-capture-loop "
        f'--lane-key "{lane_key}" --latest-signals 500 --latest-scans 1000 '
        "--max-iterations 720 --sleep-seconds 60 --iteration-timeout-seconds 30 --heartbeat-every 1 "
        "--run-capture-loop --record-capture --confirm-short-paper-capture "
        f'"{CONFIRM_SHORT_PAPER_CAPTURE_PHRASE}"'
    )


def _r158_recheck_command(lane_key: str) -> str:
    return (
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
        "--log-dir logs/hammer_radar_forward short-evidence-recheck-packet "
        f'--lane-key "{lane_key}" --latest-captures 200 --latest-outcomes 10000 --latest-signals 3000 --latest-betrayal 5000'
    )


def _r159_rehearsal_command(lane_key: str) -> str:
    return (
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
        "--log-dir logs/hammer_radar_forward fundless-short-tiny-live-readiness-rehearsal "
        f'--lane-key "{lane_key}" --latest-captures 200 --latest-outcomes 10000 --latest-signals 3000'
    )


def _record_command(lane_key: str) -> str:
    return (
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
        "--log-dir logs/hammer_radar_forward fundless-short-dry-run-packet "
        f'--lane-key "{lane_key}" --latest-captures 200 --latest-outcomes 10000 --latest-signals 3000 '
        "--record-packet --confirm-fundless-short-dry-run "
        f'"{CONFIRM_FUNDLESS_SHORT_DRY_RUN_PACKET_RECORDING_PHRASE}"'
    )


def _do_not_run_yet() -> list[str]:
    return [
        "live-connector-submit",
        "any order endpoint",
        "global live flag arming",
        "kill switch disable",
        "set short lane tiny_live",
        "set new lane tiny_live",
        "funds-dependent execution",
        "signed order request",
        "protective order submit",
    ]


def _blockers(
    *,
    matrix: Mapping[str, Any],
    target_family: Mapping[str, Any],
    readiness: str,
) -> list[str]:
    blockers: list[str] = []
    if target_family.get("current_mode") != "paper":
        blockers.append("target lane must remain paper")
    if target_family.get("direction") != "short":
        blockers.append("target lane is not short")
    for key, phrase in [
        ("fresh_evidence", "fresh captures >= 10 and R158 promotion readiness required"),
        ("funding", "account balance not verified"),
        ("risk_contract", "8m short tiny-live risk contract missing or not reviewed"),
        ("protective_policy", "short-specific protective policy not reviewed"),
        ("operator_approval", "explicit future operator approval not provided"),
        ("global_live_flags", "global live flags must remain disabled until later authorized phase"),
    ]:
        if dict(matrix.get(key) or {}).get("satisfied") is not True:
            blockers.append(phrase)
    if readiness == UNKNOWN_NEEDS_MANUAL_REVIEW:
        blockers.append("manual review required before any future live discussion")
    return _dedupe(blockers)


def _recommended_next_operator_move(readiness: str, *, matrix: Mapping[str, Any]) -> str:
    if dict(matrix.get("fresh_evidence") or {}).get("satisfied") is not True:
        return KEEP_R157_RUNNING
    if dict(matrix.get("funding") or {}).get("satisfied") is not True:
        return FUND_ACCOUNT_LATER
    if dict(matrix.get("risk_contract") or {}).get("satisfied") is not True:
        return RUN_R161_RISK_CONTRACT_DRAFT_PREVIEW
    if readiness == PACKET_READY_BUT_EXECUTION_BLOCKED:
        return RUN_R161_RISK_CONTRACT_DRAFT_PREVIEW
    return RUN_R158_RECHECK_AFTER_MORE_CAPTURES


def _recommended_next_engineering_move(readiness: str) -> str:
    if readiness == NOT_READY_MULTIPLE_BLOCKERS:
        return "Keep R157 running, keep funding read-only, and prepare R161 risk-contract draft preview only."
    if readiness == NOT_READY_EVIDENCE_BLOCKED:
        return "Run R158 recheck after more R157 captures; do not mutate lane config."
    if readiness == NOT_READY_FUNDING_BLOCKED:
        return "Define read-only funding verification in a later phase; no Binance trading calls."
    if readiness == NOT_READY_RISK_CONTRACT_BLOCKED:
        return "Build R161 8m short risk-contract draft preview only; no config write by default."
    if readiness == NOT_READY_PROTECTIVE_POLICY_BLOCKED:
        return "Draft short protective-policy review requirements before any live discussion."
    if readiness == PACKET_READY_BUT_EXECUTION_BLOCKED:
        return "Proceed only to R161 preview/checklist work; execution remains blocked."
    return "Manually review R160 inputs before further readiness work."


def _target_from_key(lane_key: str, *, mode: str) -> dict[str, Any]:
    parts = str(lane_key).split("|")
    return {
        "lane_key": lane_key,
        "symbol": parts[0] if len(parts) > 0 else "BTCUSDT",
        "timeframe": parts[1] if len(parts) > 1 else "8m",
        "direction": parts[2] if len(parts) > 2 else "short",
        "entry_mode": parts[3] if len(parts) > 3 else "ladder_close_50_618",
        "current_mode": mode,
    }


def _number_or_default(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(str(item) for item in items if str(item)))


def _sanitize(payload: Any) -> Any:
    if isinstance(payload, Mapping):
        return {str(key): _sanitize(value) for key, value in payload.items()}
    if isinstance(payload, list):
        return [_sanitize(value) for value in payload]
    return payload
