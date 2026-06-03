"""R178 risk-contract apply packet for BTCUSDT 8m short.

This module builds a future risk-contract apply packet from existing local
evidence, draft, and review surfaces. It is packet/review only: it can append
one local packet ledger after exact recording-only confirmation, but it never
writes risk-contract config, mutates lane controls, calls Binance, creates
payloads, changes lane mode, disables safety locks, or authorizes execution.
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
from src.app.hammer_radar.operator.evidence_threshold_recheck_8m_short import (
    LEDGER_FILENAME as EVIDENCE_THRESHOLD_RECHECK_LEDGER_FILENAME,
    build_evidence_threshold_recheck_8m_short,
)
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.funding_gate_role_specific_sync import ACCOUNT_NOT_FUNDED
from src.app.hammer_radar.operator.fundless_short_tiny_live_readiness_rehearsal import RISK_CONTRACT_CONFIG_PATH
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.short_risk_contract_apply_review import (
    LEDGER_FILENAME as SHORT_RISK_CONTRACT_APPLY_REVIEW_LEDGER_FILENAME,
    build_short_risk_contract_apply_review,
    build_future_config_patch_preview as build_r162_future_config_patch_preview,
    load_short_risk_contract_apply_review_records,
)
from src.app.hammer_radar.operator.short_risk_contract_draft_preview import (
    LEDGER_FILENAME as SHORT_RISK_CONTRACT_DRAFT_LEDGER_FILENAME,
    TARGET_CANDIDATE_ID,
    build_short_risk_contract_draft_preview,
    build_target_short_contract_draft,
    load_short_risk_contract_draft_records,
)
from src.app.hammer_radar.operator.short_strategy_packet import DEFAULT_TARGET_LANE_KEY, build_short_strategy_target_family

RISK_CONTRACT_APPLY_PACKET_READY = "RISK_CONTRACT_APPLY_PACKET_READY"
RISK_CONTRACT_APPLY_PACKET_REJECTED = "RISK_CONTRACT_APPLY_PACKET_REJECTED"
RISK_CONTRACT_APPLY_PACKET_RECORDED = "RISK_CONTRACT_APPLY_PACKET_RECORDED"
RISK_CONTRACT_APPLY_PACKET_BLOCKED = "RISK_CONTRACT_APPLY_PACKET_BLOCKED"
RISK_CONTRACT_APPLY_PACKET_ERROR = "RISK_CONTRACT_APPLY_PACKET_ERROR"

APPLY_PACKET_BLOCKED_BY_EVIDENCE = "APPLY_PACKET_BLOCKED_BY_EVIDENCE"
APPLY_PACKET_BLOCKED_BY_FUNDING = "APPLY_PACKET_BLOCKED_BY_FUNDING"
APPLY_PACKET_BLOCKED_BY_OPERATOR_APPROVAL = "APPLY_PACKET_BLOCKED_BY_OPERATOR_APPROVAL"
APPLY_PACKET_BLOCKED_BY_MULTIPLE_GATES = "APPLY_PACKET_BLOCKED_BY_MULTIPLE_GATES"
APPLY_PACKET_READY_FOR_FUTURE_CONFIG_REVIEW = "APPLY_PACKET_READY_FOR_FUTURE_CONFIG_REVIEW"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

KEEP_WATCHER_RUNNING = "KEEP_WATCHER_RUNNING"
RUN_R177_AFTER_10_CAPTURES = "RUN_R177_AFTER_10_CAPTURES"
FUND_ACCOUNT_LATER = "FUND_ACCOUNT_LATER"
RUN_R179_APPLY_RISK_CONTRACT_WHEN_READY = "RUN_R179_APPLY_RISK_CONTRACT_WHEN_READY"

EVENT_TYPE = "RISK_CONTRACT_APPLY_PACKET_8M_SHORT"
LEDGER_FILENAME = "risk_contract_apply_packets_8m_short.ndjson"
CONFIRM_RISK_CONTRACT_APPLY_PACKET_RECORDING_PHRASE = (
    "I CONFIRM RISK CONTRACT APPLY PACKET RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

SAFETY = {
    **SAFETY_FALSE,
    "env_written": False,
    "env_mutated": False,
    "config_written": False,
    "risk_contract_config_written": False,
    "lane_config_written": False,
    "order_placed": False,
    "real_order_placed": False,
    "execution_attempted": False,
    "order_payload_created": False,
    "executable_payload_created": False,
    "signed_order_request_created": False,
    "signed_trading_request_created": False,
    "signed_readonly_request_created": False,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "transfer_endpoint_called": False,
    "withdraw_endpoint_called": False,
    "secrets_shown": False,
    "global_live_flags_changed": False,
    "kill_switch_disabled": False,
    "paper_live_separation_intact": True,
}

SOURCE_SURFACES_USED = [
    "configs/hammer_radar/lane_controls.json",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
    "src/app/hammer_radar/operator/evidence_threshold_recheck_8m_short.py",
    "src/app/hammer_radar/operator/capture_count_sync_8m_short.py",
    "src/app/hammer_radar/operator/funding_gate_role_specific_sync.py",
    "src/app/hammer_radar/operator/short_risk_contract_draft_preview.py",
    "src/app/hammer_radar/operator/short_risk_contract_apply_review.py",
    f"logs/hammer_radar_forward/{EVIDENCE_THRESHOLD_RECHECK_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{SHORT_RISK_CONTRACT_DRAFT_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{SHORT_RISK_CONTRACT_APPLY_REVIEW_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_risk_contract_apply_packet_8m_short(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    latest_captures: int = 1000,
    latest_drafts: int = 50,
    latest_reviews: int = 50,
    record_packet: bool = False,
    confirm_risk_contract_apply_packet: str | None = None,
    config_path: str | Path | None = None,
    risk_contract_config_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_risk_contract_apply_packet == CONFIRM_RISK_CONTRACT_APPLY_PACKET_RECORDING_PHRASE
    risk_path = Path(risk_contract_config_path) if risk_contract_config_path is not None else RISK_CONTRACT_CONFIG_PATH
    try:
        target = build_short_strategy_target_family(lane_key=lane_key, config_path=config_path)
        evidence_recheck = build_evidence_threshold_recheck_8m_short(
            log_dir=resolved_log_dir,
            lane_key=target["lane_key"],
            latest_captures=latest_captures,
            record_recheck=False,
            config_path=config_path,
            risk_contract_config_path=risk_path,
            now=generated_at,
        )
        evidence_gate = build_evidence_gate_for_apply_packet(evidence_recheck)
        funding_gate = build_funding_gate_for_apply_packet(evidence_recheck)
        latest_draft = load_latest_risk_contract_draft_preview(
            log_dir=resolved_log_dir,
            lane_key=target["lane_key"],
            latest_drafts=latest_drafts,
        )
        source_draft = build_short_risk_contract_draft_preview(
            log_dir=resolved_log_dir,
            lane_key=target["lane_key"],
            record_draft=False,
            config_path=config_path,
            risk_contract_config_path=risk_path,
            now=generated_at,
        )
        risk_contract_draft = build_risk_contract_draft_summary(
            latest_draft=latest_draft,
            source_draft_preview=source_draft,
            target_family=target,
        )
        latest_review = load_latest_risk_contract_apply_review(
            log_dir=resolved_log_dir,
            lane_key=target["lane_key"],
            latest_reviews=latest_reviews,
        )
        source_apply_review = build_short_risk_contract_apply_review(
            log_dir=resolved_log_dir,
            lane_key=target["lane_key"],
            latest_captures=latest_captures,
            latest_drafts=latest_drafts,
            record_review=False,
            config_path=config_path,
            risk_contract_config_path=risk_path,
            now=generated_at,
        )
        future_patch = build_risk_contract_config_patch_preview(
            target_family=target,
            risk_contract_draft=risk_contract_draft,
            source_draft_preview=source_draft,
            source_apply_review=source_apply_review,
            config_path=risk_path,
        )
        blockers = build_apply_packet_blockers(
            target_family=target,
            evidence_gate=evidence_gate,
            funding_gate=funding_gate,
            risk_contract_draft=risk_contract_draft,
            future_config_patch_preview=future_patch,
        )
        readiness = classify_risk_contract_apply_packet_readiness(
            evidence_gate=evidence_gate,
            funding_gate=funding_gate,
            operator_approval_present=False,
            target_family=target,
        )
        status = (
            RISK_CONTRACT_APPLY_PACKET_READY
            if readiness == APPLY_PACKET_READY_FOR_FUTURE_CONFIG_REVIEW
            else RISK_CONTRACT_APPLY_PACKET_BLOCKED
        )
        if record_packet and not confirmation_valid:
            status = RISK_CONTRACT_APPLY_PACKET_REJECTED
        elif record_packet and confirmation_valid:
            status = RISK_CONTRACT_APPLY_PACKET_RECORDED

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "packet_recorded": False,
            "packet_id": None,
            "record_packet_requested": bool(record_packet),
            "confirmation_valid": bool(confirmation_valid),
            "target_family": {
                "lane_key": target.get("lane_key"),
                "symbol": target.get("symbol"),
                "timeframe": target.get("timeframe"),
                "direction": target.get("direction"),
                "entry_mode": target.get("entry_mode"),
                "current_mode": target.get("current_mode"),
            },
            "evidence_gate": evidence_gate,
            "funding_gate": funding_gate,
            "risk_contract_draft": risk_contract_draft,
            "latest_risk_contract_apply_review": latest_review,
            "future_config_patch_preview": future_patch,
            "apply_packet_readiness": readiness,
            "live_execution_allowed": False,
            "blockers": blockers,
            "future_apply_conditions": build_future_apply_conditions(),
            "recommended_next_operator_move": _recommended_next_operator_move(readiness, evidence_gate=evidence_gate),
            "recommended_next_engineering_move": _recommended_next_engineering_move(readiness),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
            "source_evidence_threshold_recheck": {
                "status": evidence_recheck.get("status"),
                "readiness": evidence_recheck.get("readiness"),
                "recheck_recorded": bool(evidence_recheck.get("recheck_recorded")),
            },
            "source_risk_contract_draft_preview": {
                "status": source_draft.get("status"),
                "readiness": source_draft.get("readiness"),
                "draft_recorded": bool(source_draft.get("draft_recorded")),
            },
            "source_risk_contract_apply_review": {
                "status": source_apply_review.get("status"),
                "readiness": source_apply_review.get("readiness"),
                "review_recorded": bool(source_apply_review.get("review_recorded")),
            },
        }
        if record_packet and confirmation_valid:
            record = append_risk_contract_apply_packet_record(payload, log_dir=resolved_log_dir)
            payload["packet_recorded"] = True
            payload["packet_id"] = record["packet_id"]
            payload["ledger_path"] = str(risk_contract_apply_packet_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": RISK_CONTRACT_APPLY_PACKET_ERROR,
                "generated_at": generated_at.isoformat(),
                "packet_recorded": False,
                "packet_id": None,
                "record_packet_requested": bool(record_packet),
                "confirmation_valid": bool(confirmation_valid),
                "target_family": _target_from_key(lane_key),
                "evidence_gate": _empty_evidence_gate(),
                "funding_gate": _empty_funding_gate(),
                "risk_contract_draft": _empty_risk_contract_draft(),
                "latest_risk_contract_apply_review": _empty_apply_review_summary(),
                "future_config_patch_preview": build_risk_contract_config_patch_preview(config_path=risk_path),
                "apply_packet_readiness": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "live_execution_allowed": False,
                "blockers": ["R178 risk-contract apply packet build error must be fixed before any future apply phase"],
                "future_apply_conditions": build_future_apply_conditions(),
                "recommended_next_operator_move": KEEP_WATCHER_RUNNING,
                "recommended_next_engineering_move": "Fix R178 packet builder error and rerun preview only; do not write config.",
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def build_evidence_gate_for_apply_packet(evidence_threshold_recheck: Mapping[str, Any] | None = None) -> dict[str, Any]:
    recheck = dict(evidence_threshold_recheck or {})
    capture = dict(recheck.get("capture_threshold_state") or {})
    return _sanitize(
        {
            "fresh_capture_count": int(capture.get("fresh_capture_count") or 0),
            "required_fresh_capture_count": int(capture.get("required_fresh_capture_count") or 10),
            "threshold_met": bool(capture.get("threshold_met")),
            "latest_captured_signal_id": capture.get("latest_captured_signal_id"),
            "source": "R177/R176",
        }
    )


def build_funding_gate_for_apply_packet(evidence_threshold_recheck: Mapping[str, Any] | None = None) -> dict[str, Any]:
    recheck = dict(evidence_threshold_recheck or {})
    funding = dict(recheck.get("funding_context") or {})
    status = funding.get("funding_status") or "UNKNOWN"
    available = funding.get("available_balance_usdt")
    if available is None and status == ACCOUNT_NOT_FUNDED:
        available = 0.0
    return _sanitize(
        {
            "funding_status": status,
            "available_balance_usdt": available,
            "funding_ready": bool(funding.get("funding_ready")),
        }
    )


def load_latest_risk_contract_draft_preview(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    latest_drafts: int = 50,
) -> dict[str, Any]:
    records = load_short_risk_contract_draft_records(log_dir=log_dir, limit=max(1, int(latest_drafts or 50)))
    for record in records:
        target = record.get("target_family") if isinstance(record.get("target_family"), Mapping) else {}
        if target.get("lane_key") == lane_key:
            return _sanitize({**dict(record), "draft_found": True, "source_ledger": SHORT_RISK_CONTRACT_DRAFT_LEDGER_FILENAME})
    return {"draft_found": False, "source_ledger": SHORT_RISK_CONTRACT_DRAFT_LEDGER_FILENAME}


def load_latest_risk_contract_apply_review(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    latest_reviews: int = 50,
) -> dict[str, Any]:
    records = load_short_risk_contract_apply_review_records(log_dir=log_dir, limit=max(1, int(latest_reviews or 50)))
    for record in records:
        target = record.get("target_family") if isinstance(record.get("target_family"), Mapping) else {}
        if target.get("lane_key") == lane_key:
            return _sanitize(
                {
                    "review_found": True,
                    "review_id": record.get("review_id"),
                    "status": record.get("status"),
                    "readiness": record.get("readiness"),
                    "blockers": list(record.get("blockers") or []),
                    "source_ledger": SHORT_RISK_CONTRACT_APPLY_REVIEW_LEDGER_FILENAME,
                }
            )
    return _empty_apply_review_summary()


def build_risk_contract_draft_summary(
    *,
    latest_draft: Mapping[str, Any] | None = None,
    source_draft_preview: Mapping[str, Any] | None = None,
    target_family: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    latest = dict(latest_draft or {})
    source = dict(source_draft_preview or {})
    draft = source.get("contract_draft") if isinstance(source.get("contract_draft"), Mapping) else {}
    if not draft:
        draft = build_target_short_contract_draft(target_family=dict(target_family or _target_from_key(DEFAULT_TARGET_LANE_KEY)))
    existing = source.get("existing_contract_summary") if isinstance(source.get("existing_contract_summary"), Mapping) else {}
    return _sanitize(
        {
            "draft_found": bool(latest.get("draft_found") or source.get("status")),
            "target_contract_exists": bool(existing.get("target_contract_exists")),
            "candidate_id": draft.get("candidate_id") or TARGET_CANDIDATE_ID,
            "max_daily_trades": draft.get("max_daily_trades"),
            "max_daily_loss_pct": draft.get("max_daily_loss_pct"),
            "require_protective_orders": bool(draft.get("require_protective_orders")),
            "short_specific_stop_tp_required": bool(draft.get("require_short_specific_stop_tp")),
            "source_draft_id": latest.get("draft_id"),
            "source_draft_status": latest.get("status") or source.get("status"),
            "source_draft_readiness": latest.get("readiness") or source.get("readiness"),
        }
    )


def build_risk_contract_config_patch_preview(
    *,
    target_family: Mapping[str, Any] | None = None,
    risk_contract_draft: Mapping[str, Any] | None = None,
    source_draft_preview: Mapping[str, Any] | None = None,
    source_apply_review: Mapping[str, Any] | None = None,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    review = dict(source_apply_review or {})
    from_review = review.get("future_config_patch_preview")
    if isinstance(from_review, Mapping) and from_review:
        preview = dict(from_review)
    else:
        target = dict(target_family or _target_from_key(DEFAULT_TARGET_LANE_KEY))
        existing = review.get("existing_contract_state") if isinstance(review.get("existing_contract_state"), Mapping) else {}
        source_draft = dict(source_draft_preview or {})
        preview = build_r162_future_config_patch_preview(
            target_family=target,
            existing_contract_state=existing,
            source_draft_preview=source_draft,
            config_path=config_path,
        )
    preview["would_write_config_now"] = False
    preview["would_modify_existing_contract"] = False
    preview["preview_only"] = True
    if "patch_preview" not in preview:
        draft = build_target_short_contract_draft(target_family=dict(target_family or _target_from_key(DEFAULT_TARGET_LANE_KEY)))
        preview["patch_preview"] = {
            "operation": "append_risk_contract_preview_only",
            "path": "risk_contracts[]",
            "value": draft,
            "apply_allowed_now": False,
        }
    patch = dict(preview.get("patch_preview") or {})
    patch["apply_allowed_now"] = False
    preview["patch_preview"] = patch
    return _sanitize(preview)


def build_apply_packet_blockers(
    *,
    target_family: Mapping[str, Any],
    evidence_gate: Mapping[str, Any],
    funding_gate: Mapping[str, Any],
    risk_contract_draft: Mapping[str, Any],
    future_config_patch_preview: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if evidence_gate.get("threshold_met") is not True:
        blockers.append("fresh captures below threshold")
    if funding_gate.get("funding_ready") is not True:
        blockers.append("funding not ready")
    if risk_contract_draft.get("draft_found") is not True:
        blockers.append("risk contract draft missing")
    if target_family.get("current_mode") != "paper":
        blockers.append("target lane must remain paper")
    blockers.extend(["operator approval missing", "config write not authorized"])
    if future_config_patch_preview.get("would_write_config_now") is not False:
        blockers.append("future patch preview attempted config write")
    return _dedupe(blockers)


def build_future_apply_conditions() -> dict[str, bool]:
    return {
        "requires_evidence_threshold": True,
        "requires_funding_ready": True,
        "requires_operator_confirmation": True,
        "requires_tests": True,
        "requires_no_live_execution_in_apply_phase": True,
        "does_not_promote_lane_mode": True,
    }


def classify_risk_contract_apply_packet_readiness(
    *,
    evidence_gate: Mapping[str, Any],
    funding_gate: Mapping[str, Any],
    operator_approval_present: bool = False,
    target_family: Mapping[str, Any] | None = None,
) -> str:
    target = dict(target_family or {})
    if target and target.get("direction") != "short":
        return UNKNOWN_NEEDS_MANUAL_REVIEW
    if evidence_gate.get("threshold_met") is not True:
        return APPLY_PACKET_BLOCKED_BY_EVIDENCE
    if funding_gate.get("funding_ready") is not True:
        return APPLY_PACKET_BLOCKED_BY_FUNDING
    if operator_approval_present is not True:
        return APPLY_PACKET_BLOCKED_BY_OPERATOR_APPROVAL
    if target and target.get("current_mode") != "paper":
        return APPLY_PACKET_BLOCKED_BY_MULTIPLE_GATES
    return APPLY_PACKET_READY_FOR_FUTURE_CONFIG_REVIEW


def append_risk_contract_apply_packet_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = risk_contract_apply_packet_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "packet_id": record.get("packet_id") or f"r178_risk_contract_apply_packet_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "record_packet_requested": bool(record.get("record_packet_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_family": dict(record.get("target_family") or {}),
            "evidence_gate": dict(record.get("evidence_gate") or {}),
            "funding_gate": dict(record.get("funding_gate") or {}),
            "risk_contract_draft": dict(record.get("risk_contract_draft") or {}),
            "latest_risk_contract_apply_review": dict(record.get("latest_risk_contract_apply_review") or {}),
            "future_config_patch_preview": dict(record.get("future_config_patch_preview") or {}),
            "apply_packet_readiness": record.get("apply_packet_readiness"),
            "live_execution_allowed": False,
            "blockers": list(record.get("blockers") or []),
            "future_apply_conditions": dict(record.get("future_apply_conditions") or {}),
            "recommended_next_operator_move": record.get("recommended_next_operator_move"),
            "recommended_next_engineering_move": record.get("recommended_next_engineering_move"),
            "do_not_run_yet": list(record.get("do_not_run_yet") or []),
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_risk_contract_apply_packet_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = risk_contract_apply_packet_records_path(get_log_dir(log_dir, use_env=True))
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


def summarize_risk_contract_apply_packets(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    readiness_counts = Counter(str(record.get("apply_packet_readiness") or "UNKNOWN") for record in records)
    latest = records[0] if records else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "readiness_counts": dict(sorted(readiness_counts.items())),
        "last_packet_id": latest.get("packet_id"),
        "last_target_lane": (latest.get("target_family") or {}).get("lane_key") if isinstance(latest.get("target_family"), Mapping) else None,
        "safety": dict(SAFETY),
    }


def risk_contract_apply_packet_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_risk_contract_apply_packet_8m_short_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _recommended_next_operator_move(readiness: str, *, evidence_gate: Mapping[str, Any]) -> str:
    if readiness == APPLY_PACKET_BLOCKED_BY_EVIDENCE:
        current = int(evidence_gate.get("fresh_capture_count") or 0)
        required = int(evidence_gate.get("required_fresh_capture_count") or 10)
        return RUN_R177_AFTER_10_CAPTURES if current >= required else KEEP_WATCHER_RUNNING
    if readiness == APPLY_PACKET_BLOCKED_BY_FUNDING:
        return FUND_ACCOUNT_LATER
    return RUN_R179_APPLY_RISK_CONTRACT_WHEN_READY


def _recommended_next_engineering_move(readiness: str) -> str:
    if readiness == APPLY_PACKET_BLOCKED_BY_EVIDENCE:
        return "Keep the R157/R176 watcher path running and rerun R177/R178 after 10 unique fresh captures."
    if readiness == APPLY_PACKET_BLOCKED_BY_FUNDING:
        return "Keep R178 preview-only and rerun funding sync only after operator-funded read-only evidence exists."
    if readiness == APPLY_PACKET_BLOCKED_BY_OPERATOR_APPROVAL:
        return "Prepare R179 config-apply-if-ready with exact confirmation, tests, no lane-mode change, and no execution."
    if readiness == APPLY_PACKET_READY_FOR_FUTURE_CONFIG_REVIEW:
        return "Open R179 as a config-only apply phase with no live execution, no lane mode change, and no Binance calls."
    return "Manually review R178 inputs before any future config apply phase."


def _do_not_run_yet() -> list[str]:
    return [
        "live-connector-submit",
        "any order endpoint",
        "global live flag arming",
        "kill switch disable",
        "set short lane tiny_live",
        "write risk contract config",
        "transfer",
        "withdraw",
    ]


def _empty_evidence_gate() -> dict[str, Any]:
    return {
        "fresh_capture_count": 0,
        "required_fresh_capture_count": 10,
        "threshold_met": False,
        "latest_captured_signal_id": None,
        "source": "R177/R176",
    }


def _empty_funding_gate() -> dict[str, Any]:
    return {"funding_status": "UNKNOWN", "available_balance_usdt": None, "funding_ready": False}


def _empty_risk_contract_draft() -> dict[str, Any]:
    return {
        "draft_found": False,
        "target_contract_exists": False,
        "candidate_id": TARGET_CANDIDATE_ID,
        "max_daily_trades": None,
        "max_daily_loss_pct": None,
        "require_protective_orders": False,
        "short_specific_stop_tp_required": False,
    }


def _empty_apply_review_summary() -> dict[str, Any]:
    return {
        "review_found": False,
        "review_id": None,
        "status": None,
        "readiness": None,
        "blockers": [],
        "source_ledger": SHORT_RISK_CONTRACT_APPLY_REVIEW_LEDGER_FILENAME,
    }


def _target_from_key(lane_key: str) -> dict[str, Any]:
    parts = str(lane_key).split("|")
    return {
        "lane_key": lane_key,
        "symbol": parts[0] if len(parts) > 0 else "BTCUSDT",
        "timeframe": parts[1] if len(parts) > 1 else "8m",
        "direction": parts[2] if len(parts) > 2 else "short",
        "entry_mode": parts[3] if len(parts) > 3 else "ladder_close_50_618",
        "current_mode": "unknown",
    }


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _sanitize(payload: Any) -> Any:
    if isinstance(payload, Mapping):
        return {str(key): _sanitize(value) for key, value in payload.items()}
    if isinstance(payload, list):
        return [_sanitize(item) for item in payload]
    if isinstance(payload, tuple):
        return [_sanitize(item) for item in payload]
    if isinstance(payload, Path):
        return str(payload)
    return payload
