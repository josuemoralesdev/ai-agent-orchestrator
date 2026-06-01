"""R159 fundless 8m short tiny-live readiness rehearsal.

This module is a diagnostic rehearsal only. It composes R158/R156/R157 local
evidence, lane controls, and local risk-contract config into a future-readiness
shell without creating order payloads, calling Binance, mutating config/env, or
authorizing execution.
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
from src.app.hammer_radar.operator.lane_control import DEFAULT_CONFIG_PATH, SAFETY_FALSE
from src.app.hammer_radar.operator.short_evidence_recheck_packet import (
    DEFAULT_LATEST_CAPTURES,
    DEFAULT_LATEST_BETRAYAL_RECHECK,
    PROMOTION_PACKET_READY_FOR_OPERATOR_REVIEW,
    build_short_evidence_recheck_packet,
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

FUNDLESS_SHORT_READINESS_REHEARSAL_READY = "FUNDLESS_SHORT_READINESS_REHEARSAL_READY"
FUNDLESS_SHORT_READINESS_REHEARSAL_REJECTED = "FUNDLESS_SHORT_READINESS_REHEARSAL_REJECTED"
FUNDLESS_SHORT_READINESS_REHEARSAL_RECORDED = "FUNDLESS_SHORT_READINESS_REHEARSAL_RECORDED"
FUNDLESS_SHORT_READINESS_REHEARSAL_BLOCKED = "FUNDLESS_SHORT_READINESS_REHEARSAL_BLOCKED"
FUNDLESS_SHORT_READINESS_REHEARSAL_ERROR = "FUNDLESS_SHORT_READINESS_REHEARSAL_ERROR"

NOT_READY_FUNDING_AND_EVIDENCE_BLOCKED = "NOT_READY_FUNDING_AND_EVIDENCE_BLOCKED"
NOT_READY_EVIDENCE_BLOCKED = "NOT_READY_EVIDENCE_BLOCKED"
NOT_READY_FUNDING_BLOCKED = "NOT_READY_FUNDING_BLOCKED"
FUNDLESS_REHEARSAL_READY = "FUNDLESS_REHEARSAL_READY"
READY_FOR_FUTURE_OPERATOR_REVIEW_ONLY = "READY_FOR_FUTURE_OPERATOR_REVIEW_ONLY"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

KEEP_R157_RUNNING = "KEEP_R157_RUNNING"
FUND_ACCOUNT_LATER = "FUND_ACCOUNT_LATER"
RUN_R160_FUNDLESS_DRY_RUN_PACKET = "RUN_R160_FUNDLESS_DRY_RUN_PACKET"
WAIT_FOR_MORE_SHORT_EVIDENCE = "WAIT_FOR_MORE_SHORT_EVIDENCE"

EVENT_TYPE = "FUNDLESS_SHORT_TINY_LIVE_READINESS_REHEARSAL"
LEDGER_FILENAME = "fundless_short_tiny_live_readiness_rehearsals.ndjson"
CONFIRM_FUNDLESS_SHORT_REHEARSAL_RECORDING_PHRASE = (
    "I CONFIRM FUNDLESS SHORT READINESS REHEARSAL RECORDING ONLY; NO LANE CHANGES; NO ORDER; NO BINANCE CALL."
)

DEFAULT_LATEST_BETRAYAL = DEFAULT_LATEST_BETRAYAL_RECHECK
RISK_CONTRACT_CONFIG_PATH = DEFAULT_CONFIG_PATH.parent / "tiny_live_risk_contracts.json"

SAFETY = {
    **SAFETY_FALSE,
    "real_order_placed": False,
    "protective_payload_created": False,
    "executable_payload_created": False,
    "signed_request_created": False,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "protective_order_endpoint_called": False,
    "paper_live_separation_intact": True,
    "env_mutated": False,
    "config_written": False,
    "global_live_flags_changed": False,
}

SOURCE_SURFACES_USED = [
    "configs/hammer_radar/lane_controls.json",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
    "logs/hammer_radar_forward/short_paper_evidence_capture.ndjson",
    "logs/hammer_radar_forward/short_evidence_recheck_packets.ndjson",
    "operator.short_evidence_recheck_packet.build_short_evidence_recheck_packet",
    "operator.short_strategy_packet.build_short_strategy_packet",
    "operator.short_paper_evidence_capture_loop.load_short_paper_evidence_capture_records",
    "operator.lane_control.load_lane_controls",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_fundless_short_tiny_live_readiness_rehearsal(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    latest_captures: int = DEFAULT_LATEST_CAPTURES,
    latest_outcomes: int = DEFAULT_LATEST_OUTCOMES,
    latest_signals: int = DEFAULT_LATEST_SIGNALS,
    latest_betrayal: int = DEFAULT_LATEST_BETRAYAL,
    record_rehearsal: bool = False,
    confirm_fundless_short_rehearsal: str | None = None,
    config_path: str | Path | None = None,
    risk_contract_config_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_fundless_short_rehearsal == CONFIRM_FUNDLESS_SHORT_REHEARSAL_RECORDING_PHRASE
    try:
        target = build_target_short_lane_state(lane_key=lane_key, config_path=config_path)
        evidence_packet = build_short_evidence_recheck_packet(
            log_dir=resolved_log_dir,
            lane_key=target["lane_key"],
            latest_captures=latest_captures,
            latest_outcomes=latest_outcomes,
            latest_signals=latest_signals,
            latest_betrayal=latest_betrayal,
            record_packet=False,
            config_path=config_path,
            now=generated_at,
        )
        evidence_gate = build_fresh_evidence_gate_summary(evidence_packet)
        funding_gate = build_funding_gate_summary()
        short_strategy_gate = build_short_strategy_gate(evidence_packet)
        risk_preview = build_short_risk_contract_preview(
            target_family=target,
            risk_contract_config_path=risk_contract_config_path,
        )
        dry_run_preview = build_non_executable_dry_run_intent_preview(target_family=target)
        readiness = classify_fundless_readiness(
            evidence_gate=evidence_gate,
            funding_gate=funding_gate,
            target_family=target,
        )
        blockers = build_fundless_readiness_blockers(
            evidence_gate=evidence_gate,
            funding_gate=funding_gate,
            target_family=target,
            risk_contract_preview=risk_preview,
            readiness=readiness,
        )
        checklist = build_operator_arming_checklist_preview(
            evidence_gate=evidence_gate,
            funding_gate=funding_gate,
            target_family=target,
            risk_contract_preview=risk_preview,
        )
        status = FUNDLESS_SHORT_READINESS_REHEARSAL_READY
        if readiness in {UNKNOWN_NEEDS_MANUAL_REVIEW} or target.get("current_mode") != "paper":
            status = FUNDLESS_SHORT_READINESS_REHEARSAL_BLOCKED
        if record_rehearsal and not confirmation_valid:
            status = FUNDLESS_SHORT_READINESS_REHEARSAL_REJECTED
        elif record_rehearsal and confirmation_valid:
            status = FUNDLESS_SHORT_READINESS_REHEARSAL_RECORDED

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "rehearsal_recorded": False,
            "rehearsal_id": None,
            "record_rehearsal_requested": bool(record_rehearsal),
            "confirmation_valid": bool(confirmation_valid),
            "target_family": target,
            "evidence_gate": evidence_gate,
            "funding_gate": funding_gate,
            "short_strategy_gate": short_strategy_gate,
            "risk_contract_preview": risk_preview,
            "non_executable_dry_run_intent_preview": dry_run_preview,
            "operator_arming_checklist": checklist,
            "readiness": readiness,
            "blockers": blockers,
            "recommended_next_operator_move": _recommended_next_operator_move(readiness, evidence_gate=evidence_gate),
            "recommended_next_engineering_move": _recommended_next_engineering_move(readiness),
            "safe_commands": _safe_commands(target["lane_key"]),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
            "source_evidence_recheck": {
                "status": evidence_packet.get("status"),
                "promotion_readiness": dict(evidence_packet.get("promotion_readiness") or {}),
                "packet_recorded": bool(evidence_packet.get("packet_recorded")),
            },
        }
        if record_rehearsal and confirmation_valid:
            record = append_fundless_readiness_rehearsal_record(payload, log_dir=resolved_log_dir)
            payload["rehearsal_recorded"] = True
            payload["rehearsal_id"] = record["rehearsal_id"]
            payload["ledger_path"] = str(fundless_readiness_rehearsal_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": FUNDLESS_SHORT_READINESS_REHEARSAL_ERROR,
                "generated_at": generated_at.isoformat(),
                "rehearsal_recorded": False,
                "rehearsal_id": None,
                "record_rehearsal_requested": bool(record_rehearsal),
                "confirmation_valid": bool(confirmation_valid),
                "target_family": _target_from_key(lane_key, mode="unknown"),
                "evidence_gate": _empty_evidence_gate(),
                "funding_gate": build_funding_gate_summary(),
                "short_strategy_gate": _empty_short_strategy_gate(),
                "risk_contract_preview": _empty_risk_contract_preview(),
                "non_executable_dry_run_intent_preview": build_non_executable_dry_run_intent_preview(
                    target_family=_target_from_key(lane_key, mode="unknown")
                ),
                "operator_arming_checklist": build_operator_arming_checklist_preview(),
                "readiness": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "blockers": ["fundless readiness rehearsal build error must be fixed before review"],
                "recommended_next_operator_move": WAIT_FOR_MORE_SHORT_EVIDENCE,
                "recommended_next_engineering_move": "Fix the R159 rehearsal builder error; do not mutate lane config.",
                "safe_commands": _safe_commands(lane_key),
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def build_target_short_lane_state(
    *,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    return build_short_strategy_target_family(lane_key=lane_key, config_path=config_path)


def build_fresh_evidence_gate_summary(evidence_recheck_packet: Mapping[str, Any] | None = None) -> dict[str, Any]:
    packet = dict(evidence_recheck_packet or {})
    fresh = dict(packet.get("fresh_evidence") or {})
    historical = dict(packet.get("historical_evidence") or {})
    promotion = dict(packet.get("promotion_readiness") or {})
    fresh_count = int(fresh.get("fresh_candidate_count") or fresh.get("fresh_capture_records_count") or 0)
    required = int(fresh.get("freshness_threshold_required") or MIN_FRESH_CANDIDATES)
    return {
        "fresh_capture_count": fresh_count,
        "required_fresh_capture_count": required,
        "fresh_evidence_threshold_met": fresh_count >= required,
        "latest_captured_signal_id": fresh.get("latest_captured_signal_id"),
        "historical_win_rate_pct": historical.get("win_rate_pct"),
        "historical_avg_pnl_pct": historical.get("avg_pnl_pct"),
        "historical_total_pnl_pct": historical.get("total_pnl_pct"),
        "evidence_ready_for_promotion_review": promotion.get("readiness") == PROMOTION_PACKET_READY_FOR_OPERATOR_REVIEW,
    }


def build_funding_gate_summary(*, funding_status: str | None = None, account_funded: bool | None = None) -> dict[str, Any]:
    status = funding_status or "UNKNOWN_NOT_CHECKED"
    funded = account_funded if account_funded is not None else None
    return {
        "account_funded": funded,
        "funding_status": status,
        "minimum_balance_required_estimate_usdt": None,
        "balance_source": "not_checked",
        "funding_ready": funded is True and status == "READ_ONLY_AVAILABLE_FUNDED",
    }


def build_short_risk_contract_preview(
    *,
    target_family: Mapping[str, Any] | None = None,
    risk_contract_config_path: str | Path | None = None,
) -> dict[str, Any]:
    target = dict(target_family or _target_from_key(DEFAULT_TARGET_LANE_KEY, mode="paper"))
    path = Path(risk_contract_config_path) if risk_contract_config_path is not None else RISK_CONTRACT_CONFIG_PATH
    contracts = _load_risk_contracts(path)
    target_ids = {
        target.get("lane_key"),
        f"normal|{target.get('lane_key')}",
    }
    matching = [
        contract
        for contract in contracts
        if str(contract.get("candidate_id") or "") in target_ids
        or (
            str(contract.get("symbol") or "").upper() == str(target.get("symbol") or "").upper()
            and str(contract.get("timeframe") or "").lower() == str(target.get("timeframe") or "").lower()
            and str(contract.get("direction") or "").lower() == str(target.get("direction") or "").lower()
            and str(contract.get("entry_mode") or "").lower() == str(target.get("entry_mode") or "").lower()
        )
    ]
    target_contract = matching[0] if matching else {}
    return {
        "risk_contract_exists": bool(contracts),
        "target_lane_has_contract": bool(target_contract),
        "suggested_tiny_live_notional_usdt": None,
        "max_daily_trades": int(target_contract.get("max_daily_trades") or 1),
        "max_daily_loss_pct": _number_or_default(target_contract.get("max_daily_loss_pct"), 0.15),
        "requires_protective_orders": bool(target_contract.get("protective_stop_required", True)),
        "non_executable_preview_only": True,
    }


def build_non_executable_dry_run_intent_preview(
    *,
    target_family: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    target = dict(target_family or _target_from_key(DEFAULT_TARGET_LANE_KEY, mode="paper"))
    return {
        "would_build_order_payload": False,
        "would_submit_order": False,
        "would_call_binance": False,
        "intent_type": "SHORT_TINY_LIVE_REHEARSAL_ONLY",
        "side": "SELL",
        "symbol": target.get("symbol") or "BTCUSDT",
        "timeframe": target.get("timeframe") or "8m",
        "entry_mode": target.get("entry_mode") or "ladder_close_50_618",
        "notional_usdt": None,
        "stop_tp_model": "short_specific_required_before_live",
        "executable": False,
    }


def build_operator_arming_checklist_preview(
    *,
    evidence_gate: Mapping[str, Any] | None = None,
    funding_gate: Mapping[str, Any] | None = None,
    target_family: Mapping[str, Any] | None = None,
    risk_contract_preview: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    evidence = dict(evidence_gate or {})
    funding = dict(funding_gate or {})
    target = dict(target_family or {})
    risk = dict(risk_contract_preview or {})
    satisfied: list[str] = []
    blocked: list[str] = []
    if target.get("current_mode") == "paper":
        satisfied.append("target short lane remains paper")
    else:
        blocked.append("target short lane must remain paper")
    if evidence.get("fresh_evidence_threshold_met") is True:
        satisfied.append("fresh captures >= 10")
    else:
        blocked.append("fresh captures >= 10")
    if funding.get("funding_ready") is True:
        satisfied.append("account funding verified")
    else:
        blocked.append("account funding verified")
    if risk.get("target_lane_has_contract") is True:
        satisfied.append("short risk contract reviewed")
    else:
        blocked.append("short risk contract reviewed")
    blocked.extend(
        [
            "protective policy reviewed",
            "global kill switch reviewed",
            "operator explicit approval",
            "live flags intentionally armed in later phase",
        ]
    )
    return {
        "required_before_future_live_discussion": [
            "fresh captures >= 10",
            "account funding verified",
            "short risk contract reviewed",
            "protective policy reviewed",
            "global kill switch reviewed",
            "operator explicit approval",
            "live flags intentionally armed in later phase",
        ],
        "currently_satisfied": _dedupe(satisfied),
        "currently_blocked": _dedupe(blocked),
    }


def build_fundless_readiness_blockers(
    *,
    evidence_gate: Mapping[str, Any] | None = None,
    funding_gate: Mapping[str, Any] | None = None,
    target_family: Mapping[str, Any] | None = None,
    risk_contract_preview: Mapping[str, Any] | None = None,
    readiness: str | None = None,
) -> list[str]:
    evidence = dict(evidence_gate or {})
    funding = dict(funding_gate or {})
    target = dict(target_family or {})
    risk = dict(risk_contract_preview or {})
    blockers: list[str] = []
    if target.get("current_mode") != "paper":
        blockers.append("target lane is not paper")
    if target.get("direction") != "short":
        blockers.append("target lane is not short")
    if evidence.get("fresh_evidence_threshold_met") is not True:
        blockers.append("fresh short capture sample below 10")
    if evidence.get("evidence_ready_for_promotion_review") is not True:
        blockers.append("R158 promotion readiness is not ready for operator review")
    if funding.get("funding_ready") is not True:
        blockers.append("account funding not verified")
    if risk.get("target_lane_has_contract") is not True:
        blockers.append("short target lane has no reviewed tiny-live risk contract")
    blockers.extend(
        [
            "protective policy must be reviewed before future live discussion",
            "global kill switch must be reviewed before future live discussion",
            "operator explicit approval is required in a later phase",
            "live flags must remain disabled until a later authorized phase",
        ]
    )
    if readiness == UNKNOWN_NEEDS_MANUAL_REVIEW:
        blockers.append("manual review required before any next readiness packet")
    return _dedupe(blockers)


def classify_fundless_readiness(
    *,
    evidence_gate: Mapping[str, Any] | None = None,
    funding_gate: Mapping[str, Any] | None = None,
    target_family: Mapping[str, Any] | None = None,
) -> str:
    evidence = dict(evidence_gate or {})
    funding = dict(funding_gate or {})
    target = dict(target_family or {})
    if target.get("direction") != "short" or target.get("current_mode") != "paper":
        return UNKNOWN_NEEDS_MANUAL_REVIEW
    evidence_ready = evidence.get("fresh_evidence_threshold_met") is True and evidence.get("evidence_ready_for_promotion_review") is True
    funding_ready = funding.get("funding_ready") is True
    if not evidence_ready and not funding_ready:
        return NOT_READY_FUNDING_AND_EVIDENCE_BLOCKED
    if not evidence_ready:
        return NOT_READY_EVIDENCE_BLOCKED
    if not funding_ready:
        return NOT_READY_FUNDING_BLOCKED
    if funding.get("account_funded") is None:
        return FUNDLESS_REHEARSAL_READY
    return READY_FOR_FUTURE_OPERATOR_REVIEW_ONLY


def append_fundless_readiness_rehearsal_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = fundless_readiness_rehearsal_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "rehearsal_id": record.get("rehearsal_id") or f"r159_fundless_short_rehearsal_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "record_rehearsal_requested": bool(record.get("record_rehearsal_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_family": dict(record.get("target_family") or {}),
            "evidence_gate": dict(record.get("evidence_gate") or {}),
            "funding_gate": dict(record.get("funding_gate") or {}),
            "short_strategy_gate": dict(record.get("short_strategy_gate") or {}),
            "risk_contract_preview": dict(record.get("risk_contract_preview") or {}),
            "non_executable_dry_run_intent_preview": dict(record.get("non_executable_dry_run_intent_preview") or {}),
            "operator_arming_checklist": dict(record.get("operator_arming_checklist") or {}),
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


def load_fundless_readiness_rehearsal_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = fundless_readiness_rehearsal_records_path(get_log_dir(log_dir, use_env=True))
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


def summarize_fundless_readiness_rehearsals(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    readiness_counts = Counter(str(record.get("readiness") or "UNKNOWN") for record in records)
    latest = records[0] if records else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "readiness_counts": dict(sorted(readiness_counts.items())),
        "last_rehearsal_id": latest.get("rehearsal_id"),
        "last_target_lane": (latest.get("target_family") or {}).get("lane_key") if isinstance(latest.get("target_family"), Mapping) else None,
        "safety": dict(SAFETY),
    }


def build_short_strategy_gate(evidence_recheck_packet: Mapping[str, Any] | None = None) -> dict[str, Any]:
    packet = dict(evidence_recheck_packet or {})
    target = dict(packet.get("target_family") or {})
    interpretation = build_short_golden_pocket_interpretation(target)
    strategy_recheck = dict(packet.get("strategy_recheck") or {})
    promotion = dict(packet.get("promotion_readiness") or {})
    return {
        "golden_pocket_role": interpretation.get("golden_pocket_role"),
        "short_specific_stop_tp_required": True,
        "short_strategy_packet_exists": bool(strategy_recheck),
        "short_strategy_ready_for_review": promotion.get("readiness") == PROMOTION_PACKET_READY_FOR_OPERATOR_REVIEW,
    }


def fundless_readiness_rehearsal_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_fundless_readiness_rehearsal_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _safe_commands(lane_key: str) -> list[str]:
    return [
        _r157_capture_command(lane_key),
        _r158_recheck_command(lane_key),
        _r156_strategy_packet_command(lane_key),
        _record_command(lane_key),
    ]


def _record_command(lane_key: str) -> str:
    return (
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
        "--log-dir logs/hammer_radar_forward fundless-short-tiny-live-readiness-rehearsal "
        f'--lane-key "{lane_key}" --latest-captures 200 --latest-outcomes 10000 --latest-signals 3000 '
        "--record-rehearsal --confirm-fundless-short-rehearsal "
        f'"{CONFIRM_FUNDLESS_SHORT_REHEARSAL_RECORDING_PHRASE}"'
    )


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


def _r156_strategy_packet_command(lane_key: str) -> str:
    return (
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
        "--log-dir logs/hammer_radar_forward short-strategy-packet "
        f'--lane-key "{lane_key}" --latest-outcomes 10000 --latest-signals 3000 --latest-betrayal 5000 --latest-watch-records 500'
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
    ]


def _recommended_next_operator_move(readiness: str, *, evidence_gate: Mapping[str, Any]) -> str:
    if not evidence_gate.get("fresh_evidence_threshold_met"):
        return KEEP_R157_RUNNING
    if readiness == NOT_READY_FUNDING_BLOCKED:
        return FUND_ACCOUNT_LATER
    if readiness in {FUNDLESS_REHEARSAL_READY, READY_FOR_FUTURE_OPERATOR_REVIEW_ONLY}:
        return RUN_R160_FUNDLESS_DRY_RUN_PACKET
    return WAIT_FOR_MORE_SHORT_EVIDENCE


def _recommended_next_engineering_move(readiness: str) -> str:
    if readiness == NOT_READY_FUNDING_AND_EVIDENCE_BLOCKED:
        return "Keep R157 running and prepare R160 non-executable dry-run packet scaffolding; do not mutate lane config."
    if readiness == NOT_READY_EVIDENCE_BLOCKED:
        return "Collect more fresh short evidence through R157 before any future operator-review packet."
    if readiness == NOT_READY_FUNDING_BLOCKED:
        return "Keep the fundless rehearsal shell ready and define funding verification in R160; no live execution."
    if readiness in {FUNDLESS_REHEARSAL_READY, READY_FOR_FUTURE_OPERATOR_REVIEW_ONLY}:
        return "Build R160 detailed non-executable dry-run packet and operator arming checklist only."
    return "Manually review R159 inputs before further readiness work."


def _load_risk_contracts(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    return [dict(row) for row in raw.get("risk_contracts") or [] if isinstance(row, Mapping)]


def _empty_evidence_gate() -> dict[str, Any]:
    return {
        "fresh_capture_count": 0,
        "required_fresh_capture_count": int(MIN_FRESH_CANDIDATES),
        "fresh_evidence_threshold_met": False,
        "latest_captured_signal_id": None,
        "historical_win_rate_pct": None,
        "historical_avg_pnl_pct": None,
        "historical_total_pnl_pct": None,
        "evidence_ready_for_promotion_review": False,
    }


def _empty_short_strategy_gate() -> dict[str, Any]:
    return {
        "golden_pocket_role": "resistance/retrace zone",
        "short_specific_stop_tp_required": True,
        "short_strategy_packet_exists": False,
        "short_strategy_ready_for_review": False,
    }


def _empty_risk_contract_preview() -> dict[str, Any]:
    return {
        "risk_contract_exists": False,
        "target_lane_has_contract": False,
        "suggested_tiny_live_notional_usdt": None,
        "max_daily_trades": 1,
        "max_daily_loss_pct": 0.15,
        "requires_protective_orders": True,
        "non_executable_preview_only": True,
    }


def _target_from_key(lane_key: str, *, mode: str) -> dict[str, Any]:
    parts = str(lane_key or DEFAULT_TARGET_LANE_KEY).split("|")
    while len(parts) < 4:
        parts.append("")
    return {
        "lane_key": "|".join(parts[:4]),
        "symbol": parts[0] or "BTCUSDT",
        "timeframe": parts[1] or "8m",
        "direction": parts[2] or "short",
        "entry_mode": parts[3] or "ladder_close_50_618",
        "current_mode": mode,
    }


def _number_or_default(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(str(item) for item in items if item))


def _sanitize(payload: Mapping[str, Any]) -> dict[str, Any]:
    rendered = json.dumps(payload, sort_keys=True, default=str).lower()
    sanitized = json.loads(json.dumps(payload, sort_keys=True, default=str))
    if any(token in rendered for token in ("api_secret", "telegram_bot_token", "signature=")):
        sanitized["secrets_shown"] = False
    return sanitized
