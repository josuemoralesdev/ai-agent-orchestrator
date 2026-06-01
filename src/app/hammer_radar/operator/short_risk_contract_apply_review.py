"""R162 8m short risk-contract apply review.

This module reviews whether the R161 draft risk contract is ready for a later
config-apply phase. It is read-only by default and can append only an apply
review record after exact recording-only confirmation. It never writes risk
contract config, mutates lane controls, creates order payloads, calls Binance,
signs requests, or enables live execution.
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
)
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.short_evidence_recheck_packet import (
    DEFAULT_LATEST_BETRAYAL_RECHECK,
    DEFAULT_LATEST_CAPTURES,
    PROMOTION_PACKET_READY_FOR_OPERATOR_REVIEW,
    build_short_evidence_recheck_packet,
)
from src.app.hammer_radar.operator.short_paper_evidence_capture_loop import CONFIRM_SHORT_PAPER_CAPTURE_PHRASE
from src.app.hammer_radar.operator.short_risk_contract_draft_preview import (
    CONFIRM_SHORT_RISK_CONTRACT_DRAFT_RECORDING_PHRASE,
    build_contract_diff_preview,
    build_existing_contract_summary,
    build_short_risk_contract_draft_preview,
    build_target_short_contract_draft,
    load_existing_tiny_live_risk_contracts,
    load_short_risk_contract_draft_records,
)
from src.app.hammer_radar.operator.short_strategy_packet import (
    DEFAULT_LATEST_OUTCOMES,
    DEFAULT_LATEST_SIGNALS,
    DEFAULT_TARGET_LANE_KEY,
    MIN_FRESH_CANDIDATES,
    build_short_strategy_target_family,
)

SHORT_RISK_CONTRACT_APPLY_REVIEW_READY = "SHORT_RISK_CONTRACT_APPLY_REVIEW_READY"
SHORT_RISK_CONTRACT_APPLY_REVIEW_REJECTED = "SHORT_RISK_CONTRACT_APPLY_REVIEW_REJECTED"
SHORT_RISK_CONTRACT_APPLY_REVIEW_RECORDED = "SHORT_RISK_CONTRACT_APPLY_REVIEW_RECORDED"
SHORT_RISK_CONTRACT_APPLY_REVIEW_BLOCKED = "SHORT_RISK_CONTRACT_APPLY_REVIEW_BLOCKED"
SHORT_RISK_CONTRACT_APPLY_REVIEW_ERROR = "SHORT_RISK_CONTRACT_APPLY_REVIEW_ERROR"

APPLY_REVIEW_BLOCKED_BY_EVIDENCE = "APPLY_REVIEW_BLOCKED_BY_EVIDENCE"
APPLY_REVIEW_BLOCKED_BY_FUNDING = "APPLY_REVIEW_BLOCKED_BY_FUNDING"
APPLY_REVIEW_BLOCKED_BY_OPERATOR_APPROVAL = "APPLY_REVIEW_BLOCKED_BY_OPERATOR_APPROVAL"
APPLY_REVIEW_BLOCKED_BY_MULTIPLE_GATES = "APPLY_REVIEW_BLOCKED_BY_MULTIPLE_GATES"
APPLY_REVIEW_READY_FOR_FUTURE_CONFIG_PHASE = "APPLY_REVIEW_READY_FOR_FUTURE_CONFIG_PHASE"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

KEEP_R157_RUNNING = "KEEP_R157_RUNNING"
RUN_R158_RECHECK_AFTER_MORE_CAPTURES = "RUN_R158_RECHECK_AFTER_MORE_CAPTURES"
WAIT_FOR_EVIDENCE_THRESHOLD = "WAIT_FOR_EVIDENCE_THRESHOLD"
RUN_R163_FUNDING_READONLY_PRECHECK = "RUN_R163_FUNDING_READONLY_PRECHECK"

EVENT_TYPE = "SHORT_RISK_CONTRACT_APPLY_REVIEW"
LEDGER_FILENAME = "short_risk_contract_apply_reviews.ndjson"
CONFIRM_SHORT_RISK_CONTRACT_APPLY_REVIEW_RECORDING_PHRASE = (
    "I CONFIRM SHORT RISK CONTRACT APPLY REVIEW RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)
FUTURE_CONFIG_APPLY_CONFIRMATION_PHRASE = (
    "I CONFIRM 8M SHORT RISK CONTRACT CONFIG APPLY ONLY; NO LANE MODE CHANGE; NO ORDER; NO BINANCE CALL."
)

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
    "risk_contract_config_written": False,
    "global_live_flags_changed": False,
}

SOURCE_SURFACES_USED = [
    "configs/hammer_radar/lane_controls.json",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
    "operator.short_risk_contract_draft_preview.build_short_risk_contract_draft_preview",
    "operator.short_risk_contract_draft_preview.load_short_risk_contract_draft_records",
    "operator.short_evidence_recheck_packet.build_short_evidence_recheck_packet",
    "operator.fundless_short_tiny_live_readiness_rehearsal.build_funding_gate_summary",
    "logs/hammer_radar_forward/short_risk_contract_draft_previews.ndjson",
    "logs/hammer_radar_forward/short_evidence_recheck_packets.ndjson",
    "logs/hammer_radar_forward/short_paper_evidence_capture.ndjson",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_short_risk_contract_apply_review(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    latest_captures: int = DEFAULT_LATEST_CAPTURES,
    latest_drafts: int = 50,
    record_review: bool = False,
    confirm_short_risk_contract_apply_review: str | None = None,
    config_path: str | Path | None = None,
    risk_contract_config_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = (
        confirm_short_risk_contract_apply_review == CONFIRM_SHORT_RISK_CONTRACT_APPLY_REVIEW_RECORDING_PHRASE
    )
    risk_path = Path(risk_contract_config_path) if risk_contract_config_path is not None else RISK_CONTRACT_CONFIG_PATH
    try:
        target = build_short_strategy_target_family(lane_key=lane_key, config_path=config_path)
        existing_config = load_existing_risk_contract_config(config_path=risk_path)
        existing_contract_state = build_existing_contract_state(
            existing_config=existing_config,
            target_family=target,
            config_path=risk_path,
        )
        latest_draft = load_latest_short_risk_contract_draft(
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
        evidence_packet = build_short_evidence_recheck_packet(
            log_dir=resolved_log_dir,
            lane_key=target["lane_key"],
            latest_captures=latest_captures,
            latest_outcomes=DEFAULT_LATEST_OUTCOMES,
            latest_signals=DEFAULT_LATEST_SIGNALS,
            latest_betrayal=DEFAULT_LATEST_BETRAYAL_RECHECK,
            record_packet=False,
            config_path=config_path,
            now=generated_at,
        )
        matrix = build_apply_readiness_matrix(
            target_family=target,
            evidence_packet=evidence_packet,
            funding_gate=build_funding_gate_summary(),
        )
        blockers = build_apply_blockers(
            target_family=target,
            existing_contract_state=existing_contract_state,
            latest_draft_summary=latest_draft,
            apply_readiness_matrix=matrix,
        )
        future_patch = build_future_config_patch_preview(
            target_family=target,
            existing_contract_state=existing_contract_state,
            latest_draft_summary=latest_draft,
            source_draft_preview=source_draft,
            config_path=risk_path,
        )
        readiness = classify_apply_review_readiness(matrix)
        status = (
            SHORT_RISK_CONTRACT_APPLY_REVIEW_READY
            if readiness == APPLY_REVIEW_READY_FOR_FUTURE_CONFIG_PHASE
            else SHORT_RISK_CONTRACT_APPLY_REVIEW_BLOCKED
        )
        if record_review and not confirmation_valid:
            status = SHORT_RISK_CONTRACT_APPLY_REVIEW_REJECTED
        elif record_review and confirmation_valid:
            status = SHORT_RISK_CONTRACT_APPLY_REVIEW_RECORDED

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "review_recorded": False,
            "review_id": None,
            "record_review_requested": bool(record_review),
            "confirmation_valid": bool(confirmation_valid),
            "target_family": target,
            "existing_contract_state": existing_contract_state,
            "latest_draft_summary": latest_draft,
            "apply_readiness_matrix": matrix,
            "future_config_patch_preview": future_patch,
            "apply_confirmation_requirements": build_apply_confirmation_requirements(),
            "readiness": readiness,
            "blockers": blockers,
            "recommended_next_operator_move": _recommended_next_operator_move(readiness, matrix=matrix),
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
            "source_draft_preview": {
                "status": source_draft.get("status"),
                "readiness": source_draft.get("readiness"),
                "draft_recorded": bool(source_draft.get("draft_recorded")),
            },
        }
        if record_review and confirmation_valid:
            record = append_short_risk_contract_apply_review_record(payload, log_dir=resolved_log_dir)
            payload["review_recorded"] = True
            payload["review_id"] = record["review_id"]
            payload["ledger_path"] = str(short_risk_contract_apply_review_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        target = _target_from_key(lane_key, mode="unknown")
        return _sanitize(
            {
                "status": SHORT_RISK_CONTRACT_APPLY_REVIEW_ERROR,
                "generated_at": generated_at.isoformat(),
                "review_recorded": False,
                "review_id": None,
                "record_review_requested": bool(record_review),
                "confirmation_valid": bool(confirmation_valid),
                "target_family": target,
                "existing_contract_state": build_existing_contract_state(
                    existing_config={},
                    target_family=target,
                    config_path=risk_path,
                ),
                "latest_draft_summary": _empty_latest_draft_summary(),
                "apply_readiness_matrix": build_apply_readiness_matrix(target_family=target),
                "future_config_patch_preview": build_future_config_patch_preview(target_family=target, config_path=risk_path),
                "apply_confirmation_requirements": build_apply_confirmation_requirements(),
                "readiness": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "blockers": ["R162 apply review build error must be fixed before any future config apply phase"],
                "recommended_next_operator_move": RUN_R158_RECHECK_AFTER_MORE_CAPTURES,
                "recommended_next_engineering_move": "Fix the R162 apply-review builder error; do not mutate config.",
                "safe_commands": _safe_commands(lane_key),
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_existing_risk_contract_config(*, config_path: str | Path | None = None) -> dict[str, Any]:
    return load_existing_tiny_live_risk_contracts(config_path=config_path)


def build_existing_contract_state(
    *,
    existing_config: Mapping[str, Any] | None = None,
    target_family: Mapping[str, Any] | None = None,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    target = dict(target_family or _target_from_key(DEFAULT_TARGET_LANE_KEY, mode="paper"))
    config = dict(existing_config or {})
    summary = build_existing_contract_summary(config, target_family=target, config_path=config_path)
    target_contract = _find_target_contract(config.get("risk_contracts") or [], target_family=target)
    return {
        "contracts_file_exists": bool(summary.get("contracts_file_exists")),
        "target_contract_exists": bool(summary.get("target_contract_exists")),
        "target_contract_enabled_for_preflight": bool(target_contract.get("enabled_for_preflight")) if target_contract else False,
        "config_path": str(Path(config_path) if config_path is not None else summary.get("config_path") or RISK_CONTRACT_CONFIG_PATH),
    }


def load_latest_short_risk_contract_draft(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    latest_drafts: int = 50,
) -> dict[str, Any]:
    records = load_short_risk_contract_draft_records(log_dir=log_dir, limit=max(1, int(latest_drafts or 50)))
    for record in records:
        target = record.get("target_family") if isinstance(record.get("target_family"), Mapping) else {}
        if target.get("lane_key") == lane_key:
            diff = record.get("contract_diff_preview") if isinstance(record.get("contract_diff_preview"), Mapping) else {}
            return {
                "draft_exists": True,
                "draft_id": record.get("draft_id"),
                "draft_status": record.get("status"),
                "draft_readiness": record.get("readiness"),
                "would_create_target_contract": bool(diff.get("would_create_target_contract")),
                "would_write_config_now": bool(diff.get("would_write_config_now")),
            }
    return _empty_latest_draft_summary()


def build_apply_readiness_matrix(
    *,
    target_family: Mapping[str, Any] | None = None,
    evidence_packet: Mapping[str, Any] | None = None,
    funding_gate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    target = dict(target_family or _target_from_key(DEFAULT_TARGET_LANE_KEY, mode="paper"))
    packet = dict(evidence_packet or {})
    fresh = dict(packet.get("fresh_evidence") or {})
    promotion = dict(packet.get("promotion_readiness") or {})
    funding = dict(funding_gate or build_funding_gate_summary())
    fresh_count = int(fresh.get("fresh_candidate_count") or 0)
    required = int(fresh.get("freshness_threshold_required") or MIN_FRESH_CANDIDATES)
    promotion_readiness = str(promotion.get("readiness") or "PROMOTION_PACKET_NOT_READY")
    return {
        "fresh_evidence": {
            "current": f"{fresh_count} / {required}",
            "satisfied": fresh_count >= required and fresh.get("freshness_threshold_met") is True,
        },
        "r158_promotion_readiness": {
            "current": promotion_readiness,
            "satisfied": promotion_readiness == PROMOTION_PACKET_READY_FOR_OPERATOR_REVIEW,
        },
        "funding": {
            "current": funding.get("funding_status") or "UNKNOWN_NOT_CHECKED",
            "satisfied": funding.get("funding_ready") is True,
        },
        "operator_approval": {
            "current": "not provided",
            "satisfied": False,
        },
        "lane_mode": {
            "current": target.get("current_mode") or "unknown",
            "required_now": "paper",
            "satisfied": target.get("current_mode") == "paper",
        },
        "config_write_authorization": {
            "current": "not authorized",
            "satisfied": False,
        },
    }


def build_apply_blockers(
    *,
    target_family: Mapping[str, Any] | None = None,
    existing_contract_state: Mapping[str, Any] | None = None,
    latest_draft_summary: Mapping[str, Any] | None = None,
    apply_readiness_matrix: Mapping[str, Any] | None = None,
) -> list[str]:
    target = dict(target_family or {})
    existing = dict(existing_contract_state or {})
    draft = dict(latest_draft_summary or {})
    matrix = dict(apply_readiness_matrix or {})
    blockers: list[str] = []
    if target.get("direction") != "short":
        blockers.append("target lane is not short")
    if dict(matrix.get("fresh_evidence") or {}).get("satisfied") is not True:
        blockers.append("fresh captures below threshold")
    if dict(matrix.get("r158_promotion_readiness") or {}).get("satisfied") is not True:
        blockers.append("R158 promotion packet not ready for operator review")
    if dict(matrix.get("funding") or {}).get("satisfied") is not True:
        blockers.append("funding not verified")
    if dict(matrix.get("operator_approval") or {}).get("satisfied") is not True:
        blockers.append("operator approval missing")
    if dict(matrix.get("lane_mode") or {}).get("satisfied") is not True:
        blockers.append("target lane must remain paper for this review")
    if dict(matrix.get("config_write_authorization") or {}).get("satisfied") is not True:
        blockers.append("config write not authorized")
    if not existing.get("target_contract_exists"):
        blockers.append("target risk contract missing")
    if not draft.get("draft_exists"):
        blockers.append("latest R161 draft record missing")
    blockers.append("future explicit config-apply confirmation missing")
    return _dedupe(blockers)


def build_future_config_patch_preview(
    *,
    target_family: Mapping[str, Any] | None = None,
    existing_contract_state: Mapping[str, Any] | None = None,
    latest_draft_summary: Mapping[str, Any] | None = None,
    source_draft_preview: Mapping[str, Any] | None = None,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    target = dict(target_family or _target_from_key(DEFAULT_TARGET_LANE_KEY, mode="paper"))
    existing = dict(existing_contract_state or {})
    latest = dict(latest_draft_summary or {})
    source = dict(source_draft_preview or {})
    draft = source.get("contract_draft") if isinstance(source.get("contract_draft"), Mapping) else {}
    if not draft:
        draft = build_target_short_contract_draft(target_family=target)
    diff = source.get("contract_diff_preview") if isinstance(source.get("contract_diff_preview"), Mapping) else {}
    if not diff:
        diff = build_contract_diff_preview(
            existing_contract_summary={
                "target_contract_exists": bool(existing.get("target_contract_exists")),
                "contracts_file_exists": bool(existing.get("contracts_file_exists")),
            },
            contract_draft=draft,
            config_path=config_path,
        )
    patch = diff.get("proposed_config_patch") if isinstance(diff.get("proposed_config_patch"), Mapping) else {}
    return {
        "would_write_config_now": False,
        "would_create_target_contract": bool(latest.get("would_create_target_contract")) if latest.get("draft_exists") else not bool(existing.get("target_contract_exists")),
        "would_modify_existing_contract": False,
        "patch_preview": dict(patch) if patch else {"operation": "append_risk_contract_preview_only", "path": "risk_contracts[]", "value": draft, "apply_allowed_now": False},
        "preview_only": True,
    }


def build_apply_confirmation_requirements() -> dict[str, Any]:
    return {
        "future_confirmation_required": True,
        "future_phrase": FUTURE_CONFIG_APPLY_CONFIRMATION_PHRASE,
        "requires_tests_before_apply": True,
        "requires_no_live_execution": True,
        "recording_only_confirmation_phrase": CONFIRM_SHORT_RISK_CONTRACT_APPLY_REVIEW_RECORDING_PHRASE,
    }


def classify_apply_review_readiness(apply_readiness_matrix: Mapping[str, Any] | None = None) -> str:
    matrix = dict(apply_readiness_matrix or {})
    evidence_blocked = (
        dict(matrix.get("fresh_evidence") or {}).get("satisfied") is not True
        or dict(matrix.get("r158_promotion_readiness") or {}).get("satisfied") is not True
    )
    funding_blocked = dict(matrix.get("funding") or {}).get("satisfied") is not True
    approval_blocked = (
        dict(matrix.get("operator_approval") or {}).get("satisfied") is not True
        or dict(matrix.get("config_write_authorization") or {}).get("satisfied") is not True
    )
    lane_blocked = dict(matrix.get("lane_mode") or {}).get("satisfied") is not True
    blocked_count = sum(bool(item) for item in [evidence_blocked, funding_blocked, approval_blocked, lane_blocked])
    if blocked_count > 1:
        return APPLY_REVIEW_BLOCKED_BY_MULTIPLE_GATES
    if evidence_blocked:
        return APPLY_REVIEW_BLOCKED_BY_EVIDENCE
    if funding_blocked:
        return APPLY_REVIEW_BLOCKED_BY_FUNDING
    if approval_blocked:
        return APPLY_REVIEW_BLOCKED_BY_OPERATOR_APPROVAL
    if lane_blocked:
        return UNKNOWN_NEEDS_MANUAL_REVIEW
    return APPLY_REVIEW_READY_FOR_FUTURE_CONFIG_PHASE


def append_short_risk_contract_apply_review_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = short_risk_contract_apply_review_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "review_id": record.get("review_id") or f"r162_short_risk_contract_apply_review_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "record_review_requested": bool(record.get("record_review_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_family": dict(record.get("target_family") or {}),
            "existing_contract_state": dict(record.get("existing_contract_state") or {}),
            "latest_draft_summary": dict(record.get("latest_draft_summary") or {}),
            "apply_readiness_matrix": dict(record.get("apply_readiness_matrix") or {}),
            "future_config_patch_preview": dict(record.get("future_config_patch_preview") or {}),
            "apply_confirmation_requirements": dict(record.get("apply_confirmation_requirements") or {}),
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


def load_short_risk_contract_apply_review_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = short_risk_contract_apply_review_records_path(get_log_dir(log_dir, use_env=True))
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


def summarize_short_risk_contract_apply_reviews(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    readiness_counts = Counter(str(record.get("readiness") or "UNKNOWN") for record in records)
    latest = records[0] if records else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "readiness_counts": dict(sorted(readiness_counts.items())),
        "last_review_id": latest.get("review_id"),
        "last_target_lane": (latest.get("target_family") or {}).get("lane_key") if isinstance(latest.get("target_family"), Mapping) else None,
        "safety": dict(SAFETY),
    }


def short_risk_contract_apply_review_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_short_risk_contract_apply_review_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _safe_commands(lane_key: str) -> list[str]:
    return [
        _r157_12h_capture_command(lane_key),
        _r158_recheck_command(lane_key),
        _r161_draft_preview_command(lane_key),
        _r162_record_command(lane_key),
    ]


def _r157_12h_capture_command(lane_key: str) -> str:
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


def _r161_draft_preview_command(lane_key: str) -> str:
    return (
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
        "--log-dir logs/hammer_radar_forward short-risk-contract-draft-preview "
        f'--lane-key "{lane_key}" --record-draft --confirm-short-risk-contract-draft '
        f'"{CONFIRM_SHORT_RISK_CONTRACT_DRAFT_RECORDING_PHRASE}"'
    )


def _r162_record_command(lane_key: str) -> str:
    return (
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
        "--log-dir logs/hammer_radar_forward short-risk-contract-apply-review "
        f'--lane-key "{lane_key}" --latest-captures 200 --latest-drafts 50 --record-review '
        f'--confirm-short-risk-contract-apply-review "{CONFIRM_SHORT_RISK_CONTRACT_APPLY_REVIEW_RECORDING_PHRASE}"'
    )


def _do_not_run_yet() -> list[str]:
    return [
        "live-connector-submit",
        "any order endpoint",
        "global live flag arming",
        "kill switch disable",
        "set short lane tiny_live",
        "set new lane tiny_live",
        "write risk contract config",
        "funds-dependent execution",
        "signed order request",
        "protective order submit",
    ]


def _recommended_next_operator_move(readiness: str, *, matrix: Mapping[str, Any]) -> str:
    if dict(matrix.get("fresh_evidence") or {}).get("satisfied") is not True:
        return KEEP_R157_RUNNING
    if dict(matrix.get("r158_promotion_readiness") or {}).get("satisfied") is not True:
        return RUN_R158_RECHECK_AFTER_MORE_CAPTURES
    if readiness == APPLY_REVIEW_BLOCKED_BY_FUNDING:
        return RUN_R163_FUNDING_READONLY_PRECHECK
    if readiness == APPLY_REVIEW_BLOCKED_BY_MULTIPLE_GATES:
        return WAIT_FOR_EVIDENCE_THRESHOLD
    return RUN_R163_FUNDING_READONLY_PRECHECK


def _recommended_next_engineering_move(readiness: str) -> str:
    if readiness == APPLY_REVIEW_READY_FOR_FUTURE_CONFIG_PHASE:
        return "Prepare a separate future config-apply phase with exact confirmation, tests, and no lane-mode or execution changes."
    if readiness == APPLY_REVIEW_BLOCKED_BY_FUNDING:
        return "Build R163 funding read-only precheck; keep R162 apply-review read-only."
    if readiness in {APPLY_REVIEW_BLOCKED_BY_EVIDENCE, APPLY_REVIEW_BLOCKED_BY_MULTIPLE_GATES}:
        return "Keep R157/R158 evidence flow active and re-run R162 after evidence, funding, and operator approval are present."
    if readiness == APPLY_REVIEW_BLOCKED_BY_OPERATOR_APPROVAL:
        return "Wait for an explicit future apply phase and confirmation; do not write config in R162."
    return "Manually review R162 inputs before any future config-apply work."


def _find_target_contract(contracts: object, *, target_family: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(contracts, list):
        return {}
    target = dict(target_family)
    target_ids = {target.get("lane_key"), f"normal|{target.get('lane_key')}"}
    for row in contracts:
        if not isinstance(row, Mapping):
            continue
        if str(row.get("candidate_id") or "") in target_ids or str(row.get("lane_key") or "") in target_ids:
            return dict(row)
        if (
            str(row.get("symbol") or "").upper() == str(target.get("symbol") or "").upper()
            and str(row.get("timeframe") or "").lower() == str(target.get("timeframe") or "").lower()
            and str(row.get("direction") or "").lower() == str(target.get("direction") or "").lower()
            and str(row.get("entry_mode") or "").lower() == str(target.get("entry_mode") or "").lower()
        ):
            return dict(row)
    return {}


def _empty_latest_draft_summary() -> dict[str, Any]:
    return {
        "draft_exists": False,
        "draft_id": None,
        "draft_status": None,
        "draft_readiness": None,
        "would_create_target_contract": False,
        "would_write_config_now": False,
    }


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
