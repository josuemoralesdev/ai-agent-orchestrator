"""R158 short evidence recheck and promotion-readiness packet.

This module is audit/packet only. It reuses R157 capture records and R156
short strategy evidence, appends an optional local packet ledger after exact
confirmation, and never creates order payloads, calls Binance, mutates env or
lane config, changes live flags, promotes shorts, or authorizes execution.
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
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.short_paper_evidence_capture_loop import (
    CONFIRM_SHORT_PAPER_CAPTURE_PHRASE,
    SHORT_PAPER_EVIDENCE_CAPTURED,
    load_short_paper_evidence_capture_records,
)
from src.app.hammer_radar.operator.short_strategy_packet import (
    DEFAULT_LATEST_BETRAYAL,
    DEFAULT_LATEST_OUTCOMES,
    DEFAULT_LATEST_SIGNALS,
    DEFAULT_TARGET_LANE_KEY,
    MIN_FRESH_CANDIDATES,
    MIN_PAPER_OUTCOMES,
    PREFERRED_WIN_RATE_PCT,
    build_short_golden_pocket_interpretation,
    build_short_strategy_packet,
    build_short_strategy_target_family,
)

SHORT_EVIDENCE_RECHECK_READY = "SHORT_EVIDENCE_RECHECK_READY"
SHORT_EVIDENCE_RECHECK_REJECTED = "SHORT_EVIDENCE_RECHECK_REJECTED"
SHORT_EVIDENCE_RECHECK_RECORDED = "SHORT_EVIDENCE_RECHECK_RECORDED"
SHORT_EVIDENCE_RECHECK_BLOCKED = "SHORT_EVIDENCE_RECHECK_BLOCKED"
SHORT_EVIDENCE_RECHECK_ERROR = "SHORT_EVIDENCE_RECHECK_ERROR"

KEEP_PAPER_ONLY_COLLECT_MORE = "KEEP_PAPER_ONLY_COLLECT_MORE"
PROMOTION_PACKET_NOT_READY = "PROMOTION_PACKET_NOT_READY"
PROMOTION_PACKET_READY_FOR_OPERATOR_REVIEW = "PROMOTION_PACKET_READY_FOR_OPERATOR_REVIEW"
SHORT_STRATEGY_REVIEW_REQUIRED = "SHORT_STRATEGY_REVIEW_REQUIRED"
DO_NOT_PROMOTE = "DO_NOT_PROMOTE"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

KEEP_R157_RUNNING = "KEEP_R157_RUNNING"
RUN_SHORT_STRATEGY_RECHECK = "RUN_SHORT_STRATEGY_RECHECK"
BUILD_FUTURE_TINY_LIVE_REVIEW_PACKET = "BUILD_FUTURE_TINY_LIVE_REVIEW_PACKET"
WAIT_FOR_MORE_SHORT_EVIDENCE = "WAIT_FOR_MORE_SHORT_EVIDENCE"

EVENT_TYPE = "SHORT_EVIDENCE_RECHECK_PACKET"
LEDGER_FILENAME = "short_evidence_recheck_packets.ndjson"
CONFIRM_SHORT_EVIDENCE_RECHECK_RECORDING_PHRASE = (
    "I CONFIRM SHORT EVIDENCE RECHECK RECORDING ONLY; NO LANE CHANGES; NO ORDER; NO BINANCE CALL."
)

DEFAULT_LATEST_CAPTURES = 200
MAX_LATEST_CAPTURES = 10000
MAX_LATEST_OUTCOMES = 100000
MAX_LATEST_SIGNALS = 50000
DEFAULT_LATEST_BETRAYAL_RECHECK = DEFAULT_LATEST_BETRAYAL
MAX_LATEST_BETRAYAL = 50000

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
    "logs/hammer_radar_forward/short_paper_evidence_capture.ndjson",
    "logs/hammer_radar_forward/short_paper_evidence_capture_heartbeats.ndjson",
    "logs/hammer_radar_forward/outcomes.ndjson",
    "logs/hammer_radar_forward/signals.ndjson",
    "logs/hammer_radar_forward/betrayal_shadow_outcomes.ndjson",
    "operator.short_paper_evidence_capture_loop.load_short_paper_evidence_capture_records",
    "operator.short_strategy_packet.build_short_strategy_packet",
    "operator.full_spectrum_betrayal_short_review",
    "operator.promotion_candidate_audit",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_short_evidence_recheck_packet(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    latest_captures: int = DEFAULT_LATEST_CAPTURES,
    latest_outcomes: int = DEFAULT_LATEST_OUTCOMES,
    latest_signals: int = DEFAULT_LATEST_SIGNALS,
    latest_betrayal: int = DEFAULT_LATEST_BETRAYAL_RECHECK,
    record_packet: bool = False,
    confirm_short_evidence_recheck: str | None = None,
    config_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_short_evidence_recheck == CONFIRM_SHORT_EVIDENCE_RECHECK_RECORDING_PHRASE
    try:
        target = build_short_strategy_target_family(lane_key=lane_key, config_path=config_path)
        captures = load_recent_short_capture_records(
            log_dir=resolved_log_dir,
            lane_key=target["lane_key"],
            limit=latest_captures,
        )
        fresh_evidence = summarize_short_fresh_evidence(captures, lane_key=target["lane_key"])
        strategy_summary = rerun_short_strategy_evidence_summary(
            log_dir=resolved_log_dir,
            lane_key=target["lane_key"],
            latest_outcomes=latest_outcomes,
            latest_signals=latest_signals,
            latest_betrayal=latest_betrayal,
            config_path=config_path,
            now=generated_at,
        )
        historical = strategy_summary["historical_evidence"]
        thresholds = build_short_recheck_thresholds()
        readiness = classify_short_promotion_readiness(
            target_family=target,
            fresh_evidence=fresh_evidence,
            historical_evidence=historical,
        )
        blockers = build_short_readiness_blockers(
            target_family=target,
            fresh_evidence=fresh_evidence,
            historical_evidence=historical,
            readiness=readiness,
        )
        assessment = build_short_promotion_readiness_assessment(
            readiness=readiness,
            blockers=blockers,
            target_family=target,
            fresh_evidence=fresh_evidence,
            historical_evidence=historical,
        )
        status = SHORT_EVIDENCE_RECHECK_READY if target.get("current_mode") == "paper" else SHORT_EVIDENCE_RECHECK_BLOCKED
        if record_packet and not confirmation_valid:
            status = SHORT_EVIDENCE_RECHECK_REJECTED
        elif record_packet and confirmation_valid:
            status = SHORT_EVIDENCE_RECHECK_RECORDED

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "packet_recorded": False,
            "packet_id": None,
            "record_packet_requested": bool(record_packet),
            "confirmation_valid": bool(confirmation_valid),
            "target_family": target,
            "fresh_evidence": fresh_evidence,
            "historical_evidence": historical,
            "short_strategy_interpretation": build_short_golden_pocket_interpretation(target),
            "promotion_readiness": assessment,
            "thresholds": thresholds,
            "recommended_next_operator_move": build_short_next_operator_move(readiness, fresh_evidence=fresh_evidence),
            "recommended_next_engineering_move": _recommended_next_engineering_move(readiness),
            "safe_commands": _safe_commands(target["lane_key"]),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
            "strategy_recheck": strategy_summary["strategy_recheck"],
        }
        if record_packet and confirmation_valid:
            record = append_short_evidence_recheck_record(payload, log_dir=resolved_log_dir)
            payload["packet_recorded"] = True
            payload["packet_id"] = record["packet_id"]
            payload["ledger_path"] = str(short_evidence_recheck_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": SHORT_EVIDENCE_RECHECK_ERROR,
                "generated_at": generated_at.isoformat(),
                "packet_recorded": False,
                "packet_id": None,
                "record_packet_requested": bool(record_packet),
                "confirmation_valid": bool(confirmation_valid),
                "target_family": {
                    "lane_key": lane_key,
                    "symbol": "BTCUSDT",
                    "timeframe": "8m",
                    "direction": "short",
                    "entry_mode": "ladder_close_50_618",
                    "current_mode": "unknown",
                },
                "fresh_evidence": _empty_fresh_evidence(),
                "historical_evidence": _empty_historical_evidence(),
                "short_strategy_interpretation": build_short_golden_pocket_interpretation({}),
                "promotion_readiness": {
                    "readiness": UNKNOWN_NEEDS_MANUAL_REVIEW,
                    "ready_for_operator_review": False,
                    "config_change_allowed_now": False,
                    "operator_approval_required": True,
                    "why": "R158 recheck hit an error before evidence could be interpreted.",
                    "blockers": ["R158 packet build error must be fixed before any future review"],
                },
                "thresholds": build_short_recheck_thresholds(),
                "recommended_next_operator_move": RUN_SHORT_STRATEGY_RECHECK,
                "recommended_next_engineering_move": "Fix the R158 packet error before any short promotion review packet.",
                "safe_commands": _safe_commands(lane_key),
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_recent_short_capture_records(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    limit: int = DEFAULT_LATEST_CAPTURES,
) -> list[dict[str, Any]]:
    bounded = _bounded_int(limit, 1, MAX_LATEST_CAPTURES, DEFAULT_LATEST_CAPTURES)
    records = load_short_paper_evidence_capture_records(log_dir=log_dir, limit=bounded)
    return [_sanitize(record) for record in records if _record_lane_key(record) == lane_key]


def summarize_short_fresh_evidence(
    records: list[Mapping[str, Any]],
    *,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
) -> dict[str, Any]:
    matching = [record for record in records if _record_lane_key(record) == lane_key]
    captured = [record for record in matching if record.get("paper_evidence_captured") is True]
    latest = captured[0] if captured else matching[0] if matching else {}
    latest_signal_id = latest.get("captured_signal_id")
    fresh_count = len({str(record.get("captured_signal_id") or record.get("capture_id")) for record in captured})
    threshold = int(MIN_FRESH_CANDIDATES)
    return _sanitize(
        {
            "fresh_capture_records_count": len(captured),
            "latest_captured_signal_id": latest_signal_id,
            "latest_capture_status": latest.get("status"),
            "fresh_candidate_count": fresh_count,
            "freshness_threshold_required": threshold,
            "freshness_threshold_met": fresh_count >= threshold,
            "capture_records_checked": len(matching),
        }
    )


def rerun_short_strategy_evidence_summary(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    latest_outcomes: int = DEFAULT_LATEST_OUTCOMES,
    latest_signals: int = DEFAULT_LATEST_SIGNALS,
    latest_betrayal: int = DEFAULT_LATEST_BETRAYAL_RECHECK,
    config_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    packet = build_short_strategy_packet(
        log_dir=log_dir,
        lane_key=lane_key,
        latest_outcomes=_bounded_int(latest_outcomes, 1, MAX_LATEST_OUTCOMES, DEFAULT_LATEST_OUTCOMES),
        latest_signals=_bounded_int(latest_signals, 1, MAX_LATEST_SIGNALS, DEFAULT_LATEST_SIGNALS),
        latest_betrayal=_bounded_int(latest_betrayal, 1, MAX_LATEST_BETRAYAL, DEFAULT_LATEST_BETRAYAL_RECHECK),
        record_packet=False,
        confirm_short_strategy_packet=None,
        config_path=config_path,
        now=now,
    )
    evidence = dict(packet.get("evidence_summary") or {})
    historical = {
        "paper_outcome_count": int(evidence.get("paper_outcome_count") or 0),
        "win_rate_pct": evidence.get("win_rate_pct"),
        "avg_pnl_pct": evidence.get("avg_pnl_pct"),
        "total_pnl_pct": evidence.get("total_pnl_pct"),
        "fill_rate_pct": evidence.get("fill_rate_pct"),
        "stop_count": int(evidence.get("stop_count") or 0),
        "sample_quality": evidence.get("sample_quality") or "NO_SHORT_EVIDENCE",
    }
    return _sanitize(
        {
            "historical_evidence": historical,
            "strategy_recheck": {
                "status": packet.get("status"),
                "readiness": packet.get("readiness"),
                "why": packet.get("why"),
                "blockers_to_tiny_live": list(packet.get("blockers_to_tiny_live") or []),
                "source_packet_recorded": bool(packet.get("packet_recorded")),
            },
        }
    )


def build_short_promotion_readiness_assessment(
    *,
    readiness: str,
    blockers: list[str],
    target_family: Mapping[str, Any] | None = None,
    fresh_evidence: Mapping[str, Any] | None = None,
    historical_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    ready = readiness == PROMOTION_PACKET_READY_FOR_OPERATOR_REVIEW
    return {
        "readiness": readiness,
        "ready_for_operator_review": ready,
        "config_change_allowed_now": False,
        "operator_approval_required": True,
        "why": _why(
            readiness,
            target_family=target_family or {},
            fresh_evidence=fresh_evidence or {},
            historical_evidence=historical_evidence or {},
        ),
        "blockers": list(blockers),
    }


def classify_short_promotion_readiness(
    *,
    target_family: Mapping[str, Any] | None = None,
    fresh_evidence: Mapping[str, Any] | None = None,
    historical_evidence: Mapping[str, Any] | None = None,
) -> str:
    target = dict(target_family or {})
    fresh = dict(fresh_evidence or {})
    historical = dict(historical_evidence or {})
    if target.get("direction") != "short" or target.get("current_mode") != "paper":
        return DO_NOT_PROMOTE
    outcomes = int(historical.get("paper_outcome_count") or 0)
    fresh_count = int(fresh.get("fresh_candidate_count") or 0)
    if outcomes <= 0 and fresh_count <= 0:
        return KEEP_PAPER_ONLY_COLLECT_MORE
    avg_pnl = _number_or_none(historical.get("avg_pnl_pct"))
    win_rate = _number_or_none(historical.get("win_rate_pct"))
    stops = int(historical.get("stop_count") or 0)
    if outcomes >= MIN_PAPER_OUTCOMES and avg_pnl is not None and avg_pnl <= 0.0:
        return DO_NOT_PROMOTE
    if outcomes and stops / outcomes > 0.5:
        return DO_NOT_PROMOTE
    if outcomes < MIN_PAPER_OUTCOMES or fresh_count < MIN_FRESH_CANDIDATES:
        return PROMOTION_PACKET_NOT_READY
    if win_rate is None or avg_pnl is None:
        return UNKNOWN_NEEDS_MANUAL_REVIEW
    if win_rate >= PREFERRED_WIN_RATE_PCT and avg_pnl > 0.0:
        return PROMOTION_PACKET_READY_FOR_OPERATOR_REVIEW
    if avg_pnl > 0.0:
        return SHORT_STRATEGY_REVIEW_REQUIRED
    return KEEP_PAPER_ONLY_COLLECT_MORE


def build_short_readiness_blockers(
    *,
    target_family: Mapping[str, Any] | None = None,
    fresh_evidence: Mapping[str, Any] | None = None,
    historical_evidence: Mapping[str, Any] | None = None,
    readiness: str | None = None,
) -> list[str]:
    target = dict(target_family or {})
    fresh = dict(fresh_evidence or {})
    historical = dict(historical_evidence or {})
    blockers: list[str] = []
    if target.get("current_mode") != "paper":
        blockers.append("target lane is not in paper mode")
    if target.get("direction") != "short":
        blockers.append("target lane is not a short lane")
    if int(fresh.get("fresh_candidate_count") or 0) < MIN_FRESH_CANDIDATES:
        blockers.append("fresh short capture sample below 10")
    if int(historical.get("paper_outcome_count") or 0) < MIN_PAPER_OUTCOMES:
        blockers.append("paper outcome sample below 30")
    avg_pnl = _number_or_none(historical.get("avg_pnl_pct"))
    if avg_pnl is None:
        blockers.append("avg_pnl_pct unavailable")
    elif avg_pnl <= 0.0:
        blockers.append("avg_pnl_pct is not positive")
    win_rate = _number_or_none(historical.get("win_rate_pct"))
    if win_rate is None or win_rate < PREFERRED_WIN_RATE_PCT:
        blockers.append("win rate below preferred 52 pct or unavailable")
    outcomes = int(historical.get("paper_outcome_count") or 0)
    stops = int(historical.get("stop_count") or 0)
    if outcomes and stops / outcomes > 0.5:
        blockers.append("stop dominance must be controlled")
    blockers.extend(
        [
            "short lane has no tiny_live authorization",
            "future operator approval is required",
            "R158 is packet-only and cannot change lane config",
            "global/protective/live gates remain separate and not cleared by this packet",
        ]
    )
    if readiness == DO_NOT_PROMOTE:
        blockers.append("readiness is DO_NOT_PROMOTE")
    if readiness == PROMOTION_PACKET_READY_FOR_OPERATOR_REVIEW:
        blockers = [item for item in blockers if item not in {"fresh short capture sample below 10", "paper outcome sample below 30", "avg_pnl_pct is not positive", "win rate below preferred 52 pct or unavailable"}]
    return _dedupe(blockers)


def build_short_next_operator_move(readiness: str, *, fresh_evidence: Mapping[str, Any] | None = None) -> str:
    fresh = int((fresh_evidence or {}).get("fresh_candidate_count") or 0)
    if readiness == PROMOTION_PACKET_READY_FOR_OPERATOR_REVIEW:
        return BUILD_FUTURE_TINY_LIVE_REVIEW_PACKET
    if readiness == SHORT_STRATEGY_REVIEW_REQUIRED:
        return RUN_SHORT_STRATEGY_RECHECK
    if readiness in {PROMOTION_PACKET_NOT_READY, KEEP_PAPER_ONLY_COLLECT_MORE} and fresh < MIN_FRESH_CANDIDATES:
        return KEEP_R157_RUNNING
    if readiness == DO_NOT_PROMOTE:
        return RUN_SHORT_STRATEGY_RECHECK
    return WAIT_FOR_MORE_SHORT_EVIDENCE


def append_short_evidence_recheck_record(record: Mapping[str, Any], *, log_dir: str | Path | None = None) -> dict[str, Any]:
    path = short_evidence_recheck_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "packet_id": record.get("packet_id") or f"r158_short_evidence_recheck_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "record_packet_requested": bool(record.get("record_packet_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_family": dict(record.get("target_family") or {}),
            "fresh_evidence": dict(record.get("fresh_evidence") or {}),
            "historical_evidence": dict(record.get("historical_evidence") or {}),
            "short_strategy_interpretation": dict(record.get("short_strategy_interpretation") or {}),
            "promotion_readiness": dict(record.get("promotion_readiness") or {}),
            "thresholds": dict(record.get("thresholds") or {}),
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


def load_short_evidence_recheck_records(*, log_dir: str | Path | None = None, limit: int = 50) -> list[dict[str, Any]]:
    path = short_evidence_recheck_records_path(get_log_dir(log_dir, use_env=True))
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


def summarize_short_evidence_recheck_records(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    readiness_counts = Counter(str((record.get("promotion_readiness") or {}).get("readiness") or "UNKNOWN") for record in records)
    latest = records[0] if records else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "readiness_counts": dict(sorted(readiness_counts.items())),
        "last_packet_id": latest.get("packet_id"),
        "last_target_lane": (latest.get("target_family") or {}).get("lane_key") if isinstance(latest.get("target_family"), Mapping) else None,
        "safety": dict(SAFETY),
    }


def build_short_recheck_thresholds() -> dict[str, Any]:
    return {
        "min_paper_outcomes": int(MIN_PAPER_OUTCOMES),
        "min_fresh_candidates": int(MIN_FRESH_CANDIDATES),
        "preferred_win_rate_pct": int(PREFERRED_WIN_RATE_PCT),
        "avg_pnl_must_be_positive": True,
        "stop_dominance_must_be_controlled": True,
    }


def short_evidence_recheck_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_short_evidence_recheck_packet_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _safe_commands(lane_key: str) -> list[str]:
    return [
        _record_command(lane_key),
        _short_paper_capture_12h_command(lane_key),
        _short_strategy_packet_command(lane_key),
        _full_spectrum_review_command(),
    ]


def _preview_command(lane_key: str) -> str:
    return (
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
        "--log-dir logs/hammer_radar_forward short-evidence-recheck-packet "
        f"--lane-key {lane_key} --latest-captures 200 --latest-outcomes 10000 "
        "--latest-signals 3000 --latest-betrayal 5000"
    )


def _record_command(lane_key: str) -> str:
    return (
        f"{_preview_command(lane_key)} --record-packet --confirm-short-evidence-recheck "
        f'"{CONFIRM_SHORT_EVIDENCE_RECHECK_RECORDING_PHRASE}"'
    )


def _short_paper_capture_12h_command(lane_key: str) -> str:
    return (
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
        "--log-dir logs/hammer_radar_forward short-paper-evidence-capture-loop "
        f'--lane-key "{lane_key}" --latest-signals 500 --latest-scans 1000 '
        "--max-iterations 720 --sleep-seconds 60 --iteration-timeout-seconds 30 --heartbeat-every 1 "
        "--run-capture-loop --record-capture --confirm-short-paper-capture "
        f'"{CONFIRM_SHORT_PAPER_CAPTURE_PHRASE}"'
    )


def _short_strategy_packet_command(lane_key: str) -> str:
    return (
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
        "--log-dir logs/hammer_radar_forward short-strategy-packet "
        f"--lane-key {lane_key} --latest-outcomes 10000 --latest-signals 3000 --latest-betrayal 5000 --latest-watch-records 500"
    )


def _full_spectrum_review_command() -> str:
    return (
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
        "--log-dir logs/hammer_radar_forward full-spectrum-betrayal-short-review "
        "--latest-outcomes 10000 --latest-signals 3000 --latest-betrayal 5000 --latest-watch-records 500 "
        "--include-paper-lanes --include-tiny-live-incumbents --include-betrayal-inverse"
    )


def _do_not_run_yet() -> list[str]:
    return [
        "live-connector-submit",
        "any order endpoint",
        "global live flag arming",
        "kill switch disable",
        "set short lane tiny_live",
        "set new lane tiny_live",
    ]


def _recommended_next_engineering_move(readiness: str) -> str:
    if readiness == PROMOTION_PACKET_READY_FOR_OPERATOR_REVIEW:
        return "Build a future short tiny-live review packet only; keep lane mode paper until explicit future operator approval."
    if readiness == SHORT_STRATEGY_REVIEW_REQUIRED:
        return "Run another short strategy recheck and inspect stop/TP assumptions before any future packet."
    if readiness in {PROMOTION_PACKET_NOT_READY, KEEP_PAPER_ONLY_COLLECT_MORE}:
        return "Keep R157 bounded capture available and collect more short paper evidence; do not mutate lane config."
    if readiness == DO_NOT_PROMOTE:
        return "Keep the short lane paper-only and review strategy assumptions before collecting more evidence."
    return "Manually inspect missing R158 evidence fields before further packet work."


def _why(
    readiness: str,
    *,
    target_family: Mapping[str, Any],
    fresh_evidence: Mapping[str, Any],
    historical_evidence: Mapping[str, Any],
) -> str:
    if target_family.get("current_mode") != "paper":
        return "The target family is not paper-only; R158 cannot build a promotion-readiness packet for it."
    if readiness == KEEP_PAPER_ONLY_COLLECT_MORE:
        return "No usable fresh short capture and historical paper evidence combination is available yet."
    if readiness == PROMOTION_PACKET_NOT_READY:
        return "Fresh or historical short evidence is still below R158 minimums; the 8m short lane remains paper."
    if readiness == PROMOTION_PACKET_READY_FOR_OPERATOR_REVIEW:
        return "Fresh capture and historical paper thresholds are met, but this is only a future operator-review packet signal."
    if readiness == SHORT_STRATEGY_REVIEW_REQUIRED:
        return "Historical paper evidence is constructive but not strong enough for a promotion packet without more strategy review."
    if readiness == DO_NOT_PROMOTE:
        return "Short evidence is negative, stop-dominated, or not a valid paper-only short target."
    return "Missing evidence fields require manual review."


def _record_lane_key(record: Mapping[str, Any]) -> str:
    for key in ("captured_lane_key", "lane_key"):
        if record.get(key):
            return str(record.get(key))
    target = record.get("target_lane") or record.get("target_family") or {}
    if isinstance(target, Mapping) and target.get("lane_key"):
        return str(target.get("lane_key"))
    return ""


def _empty_fresh_evidence() -> dict[str, Any]:
    return {
        "fresh_capture_records_count": 0,
        "latest_captured_signal_id": None,
        "latest_capture_status": None,
        "fresh_candidate_count": 0,
        "freshness_threshold_required": int(MIN_FRESH_CANDIDATES),
        "freshness_threshold_met": False,
        "capture_records_checked": 0,
    }


def _empty_historical_evidence() -> dict[str, Any]:
    return {
        "paper_outcome_count": 0,
        "win_rate_pct": None,
        "avg_pnl_pct": None,
        "total_pnl_pct": None,
        "fill_rate_pct": None,
        "stop_count": 0,
        "sample_quality": "NO_SHORT_EVIDENCE",
    }


def _bounded_int(value: int, minimum: int, maximum: int, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _number_or_none(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value
