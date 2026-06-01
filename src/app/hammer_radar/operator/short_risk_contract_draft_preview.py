"""R161 8m short risk-contract draft preview.

This module drafts a non-executable risk-contract preview for the BTCUSDT 8m
short lane. It reads local evidence/config surfaces and may append a draft
record after exact confirmation, but it never writes risk-contract config,
changes lane modes, builds order payloads, calls Binance, signs requests, or
enables live execution.
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
from src.app.hammer_radar.operator.fundless_short_dry_run_packet import (
    build_fundless_short_dry_run_packet,
)
from src.app.hammer_radar.operator.fundless_short_tiny_live_readiness_rehearsal import (
    RISK_CONTRACT_CONFIG_PATH,
)
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.short_evidence_recheck_packet import DEFAULT_LATEST_CAPTURES
from src.app.hammer_radar.operator.short_paper_evidence_capture_loop import CONFIRM_SHORT_PAPER_CAPTURE_PHRASE
from src.app.hammer_radar.operator.short_strategy_packet import (
    DEFAULT_LATEST_OUTCOMES,
    DEFAULT_LATEST_SIGNALS,
    DEFAULT_TARGET_LANE_KEY,
    MIN_FRESH_CANDIDATES,
    MIN_PAPER_OUTCOMES,
    PREFERRED_WIN_RATE_PCT,
    build_short_golden_pocket_interpretation,
    build_short_strategy_target_family,
)

SHORT_RISK_CONTRACT_DRAFT_PREVIEW_READY = "SHORT_RISK_CONTRACT_DRAFT_PREVIEW_READY"
SHORT_RISK_CONTRACT_DRAFT_PREVIEW_REJECTED = "SHORT_RISK_CONTRACT_DRAFT_PREVIEW_REJECTED"
SHORT_RISK_CONTRACT_DRAFT_PREVIEW_RECORDED = "SHORT_RISK_CONTRACT_DRAFT_PREVIEW_RECORDED"
SHORT_RISK_CONTRACT_DRAFT_PREVIEW_BLOCKED = "SHORT_RISK_CONTRACT_DRAFT_PREVIEW_BLOCKED"
SHORT_RISK_CONTRACT_DRAFT_PREVIEW_ERROR = "SHORT_RISK_CONTRACT_DRAFT_PREVIEW_ERROR"

DRAFT_READY_CONFIG_WRITE_BLOCKED = "DRAFT_READY_CONFIG_WRITE_BLOCKED"
DRAFT_BLOCKED_BY_MISSING_EVIDENCE = "DRAFT_BLOCKED_BY_MISSING_EVIDENCE"
DRAFT_BLOCKED_BY_MISSING_BASE_CONFIG = "DRAFT_BLOCKED_BY_MISSING_BASE_CONFIG"
DRAFT_REQUIRES_OPERATOR_REVIEW = "DRAFT_REQUIRES_OPERATOR_REVIEW"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

KEEP_R157_RUNNING = "KEEP_R157_RUNNING"
RUN_R158_RECHECK_AFTER_MORE_CAPTURES = "RUN_R158_RECHECK_AFTER_MORE_CAPTURES"
RUN_R162_RISK_CONTRACT_APPLY_REVIEW_IF_READY = "RUN_R162_RISK_CONTRACT_APPLY_REVIEW_IF_READY"
WAIT_FOR_MORE_EVIDENCE = "WAIT_FOR_MORE_EVIDENCE"

EVENT_TYPE = "SHORT_RISK_CONTRACT_DRAFT_PREVIEW"
LEDGER_FILENAME = "short_risk_contract_draft_previews.ndjson"
CONFIRM_SHORT_RISK_CONTRACT_DRAFT_RECORDING_PHRASE = (
    "I CONFIRM SHORT RISK CONTRACT DRAFT RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

TARGET_CANDIDATE_ID = "normal|BTCUSDT|8m|short|ladder_close_50_618"

SAFETY = {
    **SAFETY_FALSE,
    "real_order_placed": False,
    "executable_payload_created": False,
    "protective_payload_created": False,
    "signed_request_created": False,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "protective_order_endpoint_called": False,
    "paper_live_separation_intact": True,
    "env_mutated": False,
    "config_written": False,
    "risk_contract_config_written": False,
    "global_live_flags_changed": False,
}

SOURCE_SURFACES_USED = [
    "configs/hammer_radar/lane_controls.json",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
    "operator.short_strategy_packet.build_short_strategy_target_family",
    "operator.short_strategy_packet.build_short_golden_pocket_interpretation",
    "operator.short_evidence_recheck_packet",
    "operator.fundless_short_tiny_live_readiness_rehearsal",
    "operator.fundless_short_dry_run_packet.build_fundless_short_dry_run_packet",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_short_risk_contract_draft_preview(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    record_draft: bool = False,
    confirm_short_risk_contract_draft: str | None = None,
    config_path: str | Path | None = None,
    risk_contract_config_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_short_risk_contract_draft == CONFIRM_SHORT_RISK_CONTRACT_DRAFT_RECORDING_PHRASE
    risk_path = Path(risk_contract_config_path) if risk_contract_config_path is not None else RISK_CONTRACT_CONFIG_PATH
    try:
        target = build_target_lane_snapshot(lane_key=lane_key, config_path=config_path)
        contracts = load_existing_tiny_live_risk_contracts(config_path=risk_path)
        existing_summary = build_existing_contract_summary(contracts, target_family=target, config_path=risk_path)
        draft = build_target_short_contract_draft(target_family=target)
        diff_preview = build_contract_diff_preview(
            existing_contract_summary=existing_summary,
            contract_draft=draft,
            config_path=risk_path,
        )
        source_packet = build_fundless_short_dry_run_packet(
            log_dir=resolved_log_dir,
            lane_key=target["lane_key"],
            latest_captures=DEFAULT_LATEST_CAPTURES,
            latest_outcomes=DEFAULT_LATEST_OUTCOMES,
            latest_signals=DEFAULT_LATEST_SIGNALS,
            record_packet=False,
            config_path=config_path,
            risk_contract_config_path=risk_path,
            now=generated_at,
        )
        gate_blockers = build_contract_gate_blockers(
            target_family=target,
            existing_contract_summary=existing_summary,
            source_dry_run_packet=source_packet,
        )
        future_requirements = build_future_apply_requirements()
        readiness = classify_contract_draft_readiness(
            target_family=target,
            existing_contract_summary=existing_summary,
            gate_blockers=gate_blockers,
        )
        status = SHORT_RISK_CONTRACT_DRAFT_PREVIEW_READY
        if readiness in {DRAFT_BLOCKED_BY_MISSING_BASE_CONFIG, UNKNOWN_NEEDS_MANUAL_REVIEW}:
            status = SHORT_RISK_CONTRACT_DRAFT_PREVIEW_BLOCKED
        if record_draft and not confirmation_valid:
            status = SHORT_RISK_CONTRACT_DRAFT_PREVIEW_REJECTED
        elif record_draft and confirmation_valid:
            status = SHORT_RISK_CONTRACT_DRAFT_PREVIEW_RECORDED

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "draft_recorded": False,
            "draft_id": None,
            "record_draft_requested": bool(record_draft),
            "confirmation_valid": bool(confirmation_valid),
            "target_family": target,
            "existing_contract_summary": existing_summary,
            "contract_draft": draft,
            "contract_diff_preview": diff_preview,
            "gate_blockers": gate_blockers,
            "future_apply_requirements": future_requirements,
            "readiness": readiness,
            "recommended_next_operator_move": _recommended_next_operator_move(readiness, gate_blockers=gate_blockers),
            "recommended_next_engineering_move": _recommended_next_engineering_move(readiness),
            "safe_commands": _safe_commands(target["lane_key"]),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
            "source_dry_run_packet": {
                "status": source_packet.get("status"),
                "readiness": source_packet.get("readiness"),
                "packet_recorded": bool(source_packet.get("packet_recorded")),
                "risk_contract_requirements": dict(source_packet.get("risk_contract_requirements") or {}),
            },
        }
        if record_draft and confirmation_valid:
            record = append_short_risk_contract_draft_record(payload, log_dir=resolved_log_dir)
            payload["draft_recorded"] = True
            payload["draft_id"] = record["draft_id"]
            payload["ledger_path"] = str(short_risk_contract_draft_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        target = _target_from_key(lane_key, mode="unknown")
        return _sanitize(
            {
                "status": SHORT_RISK_CONTRACT_DRAFT_PREVIEW_ERROR,
                "generated_at": generated_at.isoformat(),
                "draft_recorded": False,
                "draft_id": None,
                "record_draft_requested": bool(record_draft),
                "confirmation_valid": bool(confirmation_valid),
                "target_family": target,
                "existing_contract_summary": build_existing_contract_summary({}, target_family=target, config_path=risk_path),
                "contract_draft": build_target_short_contract_draft(target_family=target),
                "contract_diff_preview": build_contract_diff_preview(config_path=risk_path),
                "gate_blockers": ["R161 risk-contract draft preview build error must be fixed before review"],
                "future_apply_requirements": build_future_apply_requirements(),
                "readiness": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "recommended_next_operator_move": RUN_R158_RECHECK_AFTER_MORE_CAPTURES,
                "recommended_next_engineering_move": "Fix the R161 draft preview builder error; do not mutate config.",
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


def load_existing_tiny_live_risk_contracts(*, config_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(config_path) if config_path is not None else RISK_CONTRACT_CONFIG_PATH
    if not path.exists():
        return {"contracts_file_exists": False, "config_path": str(path), "funding_config": {}, "risk_contracts": []}
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        payload = {}
    contracts = payload.get("risk_contracts") if isinstance(payload.get("risk_contracts"), list) else []
    return {
        "contracts_file_exists": True,
        "config_path": str(path),
        "funding_config": dict(payload.get("funding_config") or {}),
        "risk_contracts": [dict(row) for row in contracts if isinstance(row, Mapping)],
    }


def build_existing_contract_summary(
    contracts_payload: Mapping[str, Any] | None = None,
    *,
    target_family: Mapping[str, Any] | None = None,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    payload = dict(contracts_payload or {})
    target = dict(target_family or _target_from_key(DEFAULT_TARGET_LANE_KEY, mode="paper"))
    path = str(Path(config_path) if config_path is not None else payload.get("config_path") or RISK_CONTRACT_CONFIG_PATH)
    contracts = [dict(row) for row in payload.get("risk_contracts", []) if isinstance(row, Mapping)]
    keys = [_contract_key(row) for row in contracts]
    target_keys = {TARGET_CANDIDATE_ID, str(target.get("lane_key") or "")}
    target_exists = any(key in target_keys for key in keys)
    return {
        "contracts_file_exists": bool(payload.get("contracts_file_exists")),
        "target_contract_exists": bool(target_exists),
        "existing_contract_keys": keys,
        "config_path": path,
        "existing_contract_count": len(contracts),
    }


def build_target_short_contract_draft(*, target_family: Mapping[str, Any] | None = None) -> dict[str, Any]:
    target = dict(target_family or _target_from_key(DEFAULT_TARGET_LANE_KEY, mode="paper"))
    interpretation = build_short_golden_pocket_interpretation(target)
    return {
        "candidate_id": TARGET_CANDIDATE_ID,
        "lane_key": target.get("lane_key") or DEFAULT_TARGET_LANE_KEY,
        "symbol": target.get("symbol") or "BTCUSDT",
        "timeframe": target.get("timeframe") or "8m",
        "direction": target.get("direction") or "short",
        "entry_mode": target.get("entry_mode") or "ladder_close_50_618",
        "mode_target": "future_tiny_live_review_only",
        "lane_mode_change_allowed_now": False,
        "current_lane_mode": target.get("current_mode") or "paper",
        "max_daily_trades": 1,
        "max_daily_loss_pct": 0.15,
        "max_position_notional_usdt": None,
        "suggested_tiny_live_notional_usdt": None,
        "leverage": None,
        "require_protective_orders": True,
        "protective_stop_required": True,
        "take_profit_required": True,
        "require_stop_loss": True,
        "require_take_profit": True,
        "require_short_specific_stop_tp": True,
        "golden_pocket_role": interpretation.get("golden_pocket_role") or "resistance/retrace zone",
        "invalidation_concept": "above relevant swing high/resistance",
        "take_profit_concept": "below entry toward downside continuation/liquidity",
        "freshness_seconds": 60,
        "cooldown_after_loss_minutes": 120,
        "min_fresh_captures_before_review": MIN_FRESH_CANDIDATES,
        "min_paper_outcomes_before_review": MIN_PAPER_OUTCOMES,
        "preferred_win_rate_pct": int(PREFERRED_WIN_RATE_PCT),
        "avg_pnl_must_be_positive": True,
        "funding_verified_required": True,
        "operator_approval_required": True,
        "global_kill_switch_required": True,
        "live_flags_required_later": True,
        "config_write_allowed_now": False,
        "execution_allowed_now": False,
        "enabled_for_preflight": False,
        "order_type": "not_created",
        "notes": "R161 preview only. Do not write config, change lane mode, create orders, or call Binance.",
    }


def build_contract_diff_preview(
    *,
    existing_contract_summary: Mapping[str, Any] | None = None,
    contract_draft: Mapping[str, Any] | None = None,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    summary = dict(existing_contract_summary or {})
    draft = dict(contract_draft or build_target_short_contract_draft())
    target_exists = bool(summary.get("target_contract_exists"))
    path = str(Path(config_path) if config_path is not None else RISK_CONTRACT_CONFIG_PATH)
    return {
        "would_create_target_contract": not target_exists,
        "would_modify_existing_contract": False,
        "would_write_config_now": False,
        "config_path": path,
        "preview_only": True,
        "proposed_config_patch": {
            "operation": "append_risk_contract_preview_only",
            "path": "risk_contracts[]",
            "value": draft,
            "apply_allowed_now": False,
        },
    }


def build_contract_gate_blockers(
    *,
    target_family: Mapping[str, Any] | None = None,
    existing_contract_summary: Mapping[str, Any] | None = None,
    source_dry_run_packet: Mapping[str, Any] | None = None,
) -> list[str]:
    target = dict(target_family or {})
    summary = dict(existing_contract_summary or {})
    source = dict(source_dry_run_packet or {})
    blockers: list[str] = []
    if not summary.get("contracts_file_exists"):
        blockers.append("base risk contract config missing")
    if target.get("current_mode") != "paper":
        blockers.append("lane must remain paper")
    if target.get("direction") != "short":
        blockers.append("target lane is not short")
    blockers.extend(
        [
            "fresh captures below threshold",
            "funding not verified",
            "operator approval missing",
            "lane remains paper",
            "config write not authorized",
        ]
    )
    for blocker in source.get("blockers", []) or []:
        text = str(blocker)
        if "fresh captures" in text and "fresh captures below threshold" not in blockers:
            blockers.append("fresh captures below threshold")
        elif "funding" in text and "funding not verified" not in blockers:
            blockers.append("funding not verified")
        elif "risk contract" in text and not summary.get("target_contract_exists"):
            blockers.append("target risk contract missing")
    return _dedupe(blockers)


def build_future_apply_requirements() -> dict[str, bool]:
    return {
        "requires_explicit_future_confirmation": True,
        "requires_r158_ready": True,
        "requires_funding_verified": True,
        "requires_operator_review": True,
        "requires_config_write_phase": True,
        "requires_no_live_execution_in_apply_phase": True,
    }


def classify_contract_draft_readiness(
    *,
    target_family: Mapping[str, Any] | None = None,
    existing_contract_summary: Mapping[str, Any] | None = None,
    gate_blockers: list[str] | None = None,
) -> str:
    target = dict(target_family or {})
    summary = dict(existing_contract_summary or {})
    blockers = set(gate_blockers or [])
    if not summary.get("contracts_file_exists"):
        return DRAFT_BLOCKED_BY_MISSING_BASE_CONFIG
    if target.get("direction") != "short" or target.get("current_mode") != "paper":
        return UNKNOWN_NEEDS_MANUAL_REVIEW
    if "fresh captures below threshold" in blockers:
        return DRAFT_BLOCKED_BY_MISSING_EVIDENCE
    if {"funding not verified", "operator approval missing", "config write not authorized"} & blockers:
        return DRAFT_REQUIRES_OPERATOR_REVIEW
    return DRAFT_READY_CONFIG_WRITE_BLOCKED


def append_short_risk_contract_draft_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = short_risk_contract_draft_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "draft_id": record.get("draft_id") or f"r161_short_risk_contract_draft_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "record_draft_requested": bool(record.get("record_draft_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_family": dict(record.get("target_family") or {}),
            "existing_contract_summary": dict(record.get("existing_contract_summary") or {}),
            "contract_draft": dict(record.get("contract_draft") or {}),
            "contract_diff_preview": dict(record.get("contract_diff_preview") or {}),
            "gate_blockers": list(record.get("gate_blockers") or []),
            "future_apply_requirements": dict(record.get("future_apply_requirements") or {}),
            "readiness": record.get("readiness"),
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


def load_short_risk_contract_draft_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = short_risk_contract_draft_records_path(get_log_dir(log_dir, use_env=True))
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


def summarize_short_risk_contract_drafts(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    readiness_counts = Counter(str(record.get("readiness") or "UNKNOWN") for record in records)
    latest = records[0] if records else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "readiness_counts": dict(sorted(readiness_counts.items())),
        "last_draft_id": latest.get("draft_id"),
        "last_target_lane": (latest.get("target_family") or {}).get("lane_key") if isinstance(latest.get("target_family"), Mapping) else None,
        "safety": dict(SAFETY),
    }


def short_risk_contract_draft_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_short_risk_contract_draft_preview_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _safe_commands(lane_key: str) -> list[str]:
    return [
        _r157_12h_capture_command(lane_key),
        _r158_recheck_command(lane_key),
        _r160_dry_run_packet_command(lane_key),
        _r161_record_command(lane_key),
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


def _r160_dry_run_packet_command(lane_key: str) -> str:
    return (
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
        "--log-dir logs/hammer_radar_forward fundless-short-dry-run-packet "
        f'--lane-key "{lane_key}" --latest-captures 200 --latest-outcomes 10000 --latest-signals 3000'
    )


def _r161_record_command(lane_key: str) -> str:
    return (
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
        "--log-dir logs/hammer_radar_forward short-risk-contract-draft-preview "
        f'--lane-key "{lane_key}" --record-draft --confirm-short-risk-contract-draft '
        f'"{CONFIRM_SHORT_RISK_CONTRACT_DRAFT_RECORDING_PHRASE}"'
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


def _recommended_next_operator_move(readiness: str, *, gate_blockers: list[str]) -> str:
    if "fresh captures below threshold" in gate_blockers:
        return KEEP_R157_RUNNING
    if readiness == DRAFT_BLOCKED_BY_MISSING_EVIDENCE:
        return RUN_R158_RECHECK_AFTER_MORE_CAPTURES
    if readiness == DRAFT_READY_CONFIG_WRITE_BLOCKED:
        return RUN_R162_RISK_CONTRACT_APPLY_REVIEW_IF_READY
    return WAIT_FOR_MORE_EVIDENCE


def _recommended_next_engineering_move(readiness: str) -> str:
    if readiness == DRAFT_BLOCKED_BY_MISSING_BASE_CONFIG:
        return "Review the base risk-contract config path before any future apply phase; do not write config in R161."
    if readiness == DRAFT_BLOCKED_BY_MISSING_EVIDENCE:
        return "Keep R157/R158 evidence flow active; R161 remains a preview-only draft."
    if readiness == DRAFT_REQUIRES_OPERATOR_REVIEW:
        return "Prepare R162 apply-review task only after evidence, funding, and operator review are present."
    if readiness == DRAFT_READY_CONFIG_WRITE_BLOCKED:
        return "Open R162 apply review with explicit no-execution constraints before any config write is considered."
    return "Manually review R161 draft inputs before further readiness work."


def _contract_key(contract: Mapping[str, Any]) -> str:
    return str(contract.get("candidate_id") or contract.get("lane_key") or "")


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
