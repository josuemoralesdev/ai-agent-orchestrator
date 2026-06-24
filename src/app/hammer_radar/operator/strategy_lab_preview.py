"""R304 paper-only Strategy Lab preview.

This module composes existing evidence surfaces into a read-only preview. It
does not promote lanes, mutate live flags, create final commands, submit
orders, call Binance, or change risk contracts.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir, load_outcomes, load_signals
from src.app.hammer_radar.operator.betrayal_paper_outcome_ledger import (
    build_betrayal_paper_outcome_status,
)
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.strategy_performance import build_live_eligibility_matrix
from src.app.hammer_radar.operator.strategy_promotion_watcher import build_strategy_promotion_status
from src.app.hammer_radar.operator.tiny_live_fresh_trigger_watch import (
    build_latest_or_not_checked_fresh_trigger_watch,
)
from src.app.hammer_radar.operator.tiny_live_strategy_lane_selection import (
    LIVE_QUALIFIED,
    NEAR_MISS_INCUBATOR,
    PAPER_ONLY,
    PREFERRED_ENTRY_MODE,
    build_exact_lane_risk_contract_status,
    build_lane_key,
)

EVENT_TYPE = "R304_STRATEGY_LAB_PREVIEW"
CREATED_BY_PHASE = "R304_PAPER_REFRESH_DURABILITY_AND_STRATEGY_LAB_PREVIEW"
LEDGER_FILENAME = "strategy_lab_preview.ndjson"

BLOCKED = "BLOCKED"
BETRAYAL_INVERSE_PREVIEW = "BETRAYAL_INVERSE_PREVIEW"

KEEP_TINY_LIVE_WAIT = "KEEP_TINY_LIVE_WAIT"
EXPANSION_PREVIEW_ONLY = "EXPANSION_PREVIEW_ONLY"
STRATEGY_LAB_REVIEW = "STRATEGY_LAB_REVIEW"
BETRAYAL_LAB_REVIEW = "BETRAYAL_LAB_REVIEW"
BLOCKED_INSUFFICIENT_EVIDENCE = "BLOCKED_INSUFFICIENT_EVIDENCE"
BLOCKED_NEGATIVE_PNL = "BLOCKED_NEGATIVE_PNL"
BLOCKED_POLICY = "BLOCKED_POLICY"

BETRAYAL_BLOCKED_PREVIEW_ONLY = "BETRAYAL_BLOCKED_PREVIEW_ONLY"
BETRAYAL_PROMOTION_CANDIDATE_FOR_FUTURE_REVIEW = "BETRAYAL_PROMOTION_CANDIDATE_FOR_FUTURE_REVIEW"
BETRAYAL_REJECTED = "BETRAYAL_REJECTED"

CURRENT_TINY_LIVE_LANE = "BTCUSDT|44m|long|ladder_close_50_618"
CURRENT_LIVE_QUALIFIED_LANES = (
    CURRENT_TINY_LIVE_LANE,
    "BTCUSDT|44m|short|ladder_close_50_618",
    "BTCUSDT|55m|long|ladder_close_50_618",
)
NEAR_MISS_INCUBATOR_LANES = (
    "BTCUSDT|22m|long|ladder_close_50_618",
    "BTCUSDT|22m|short|ladder_close_50_618",
    "BTCUSDT|8m|short|ladder_close_50_618",
)
PAPER_ONLY_REVIEW_LANES = tuple(
    build_lane_key(symbol="BTCUSDT", timeframe=timeframe, direction=direction)
    for timeframe in ("4m", "8m", "13m", "88m", "222m", "444m", "888m", "4H", "13H", "13D")
    for direction in ("long", "short")
)

SAFETY = {
    "live_execution_enabled": False,
    "allow_live_orders": False,
    "global_kill_switch": True,
    "order_placed": False,
    "real_order_placed": False,
    "execution_attempted": False,
    "submit_allowed": False,
    "final_command_available": False,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "leverage_change_called": False,
    "margin_change_called": False,
    "order_payload_created": False,
    "executable_payload_created": False,
    "signed_order_request_created": False,
    "signed_trading_request_created": False,
    "secrets_shown": False,
    "secret_values_in_output": False,
    "kill_switch_disabled": False,
    "global_live_flags_changed": False,
    "paper_live_separation_intact": True,
    "real_order_forbidden": True,
}


def build_strategy_lab_preview(
    *,
    log_dir: str | Path | None = None,
    write: bool = True,
    now: datetime | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    generated_at = now or datetime.now(UTC)
    evidence_by_lane = _strategy_evidence_by_lane(resolved_log_dir)
    fresh_watch = build_latest_or_not_checked_fresh_trigger_watch(log_dir=resolved_log_dir)
    current_fresh_lane = str(fresh_watch.get("current_candidate_lane_key") or "")

    lane_keys = _ordered_lane_keys(evidence_by_lane)
    candidates = [
        _candidate_preview(
            lane_key=lane_key,
            evidence=evidence_by_lane.get(lane_key, {}),
            log_dir=resolved_log_dir,
            current_fresh_lane=current_fresh_lane,
        )
        for lane_key in lane_keys
    ]
    betrayal_candidates = _betrayal_previews(resolved_log_dir)
    payload = {
        "event_type": EVENT_TYPE,
        "created_by_phase": CREATED_BY_PHASE,
        "preview_id": f"r304_strategy_lab_preview_{uuid4().hex}",
        "generated_at": generated_at.isoformat(),
        "archive_log_dir": str(resolved_log_dir),
        "strategy_lab_preview_path": str(strategy_lab_preview_path(resolved_log_dir)),
        "current_tiny_live_lane": CURRENT_TINY_LIVE_LANE,
        "current_fresh_candidate_lane_key": current_fresh_lane or None,
        "candidate_count": len(candidates),
        "betrayal_preview_count": len(betrayal_candidates),
        "preview_candidates": candidates,
        "top_preview_candidates": _top_candidates(candidates),
        "betrayal_preview_candidates": betrayal_candidates,
        "safety": dict(SAFETY),
        "live_execution_enabled": False,
        "allow_live_orders": False,
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "submit_allowed": False,
        "final_command_available": False,
        "real_order_forbidden": True,
        "source_surfaces_used": [
            "logs/hammer_radar_forward/strategy_promotion_status.ndjson",
            "logs/hammer_radar_forward/strategy_promotion_events.ndjson",
            "logs/hammer_radar_forward/strategy_performance.ndjson",
            "logs/hammer_radar_forward/outcomes.ndjson",
            "logs/hammer_radar_forward/signals.ndjson",
            "logs/hammer_radar_forward/betrayal_true_paper_outcomes.ndjson",
            "configs/hammer_radar/autonomous_arming_state.json",
            "configs/hammer_radar/tiny_live_risk_contracts.json",
        ],
    }
    if write:
        append_strategy_lab_preview(payload, log_dir=resolved_log_dir)
    return _sanitize(payload)


def append_strategy_lab_preview(record: Mapping[str, Any], *, log_dir: str | Path) -> None:
    path = strategy_lab_preview_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def load_strategy_lab_preview_records(*, log_dir: str | Path | None = None, limit: int = 20) -> list[dict[str, Any]]:
    return read_recent_ndjson_records(strategy_lab_preview_path(get_log_dir(log_dir, use_env=True)), limit=limit)


def strategy_lab_preview_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_strategy_lab_preview_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def _strategy_evidence_by_lane(log_dir: Path) -> dict[str, dict[str, Any]]:
    evidence: dict[str, dict[str, Any]] = {}
    for row in build_live_eligibility_matrix(log_dir=log_dir).get("recommendations") or []:
        if isinstance(row, Mapping):
            _merge_evidence(evidence, row, source="computed_live_eligibility_matrix")
    status = build_strategy_promotion_status(log_dir=log_dir)
    for bucket in ("live_qualified_lanes", "near_miss_incubator_lanes", "paper_only_lanes"):
        for row in status.get(bucket) or []:
            if isinstance(row, Mapping):
                _merge_evidence(evidence, row, source=f"strategy_promotion_status.{bucket}")
    for path_name in ("strategy_promotion_status.ndjson", "strategy_promotion_events.ndjson", "strategy_performance.ndjson"):
        path = log_dir / path_name
        for record in read_recent_ndjson_records(path, limit=200):
            for row in _candidate_rows(record):
                _merge_evidence(evidence, row, source=str(path))
    return evidence


def _merge_evidence(target: dict[str, dict[str, Any]], row: Mapping[str, Any], *, source: str) -> None:
    lane_key = _lane_key(row)
    if not lane_key:
        return
    existing = target.get(lane_key, {})
    incoming = dict(row)
    existing_sample = _int_or_none(existing.get("sample_count") or existing.get("samples")) or -1
    incoming_sample = _int_or_none(incoming.get("sample_count") or incoming.get("samples")) or -1
    if existing and incoming_sample < existing_sample:
        merged = {**incoming, **existing}
    else:
        merged = {**existing, **incoming}
    sources = list(existing.get("_source_chain") or [])
    sources.append(source)
    merged["_source_chain"] = list(dict.fromkeys(sources))
    target[lane_key] = merged


def _candidate_rows(record: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = [record]
    for key in ("promotion_ready", "near_promotion", "blocked_candidates", "recommendations"):
        value = record.get(key)
        if isinstance(value, list):
            rows.extend(item for item in value if isinstance(item, Mapping))
    watch = record.get("qualified_candidate_watch")
    if isinstance(watch, Mapping):
        for key in ("live_qualified_lanes", "near_miss_incubator_lanes", "paper_only_lanes"):
            value = watch.get(key)
            if isinstance(value, list):
                rows.extend(item for item in value if isinstance(item, Mapping))
    return rows


def _ordered_lane_keys(evidence_by_lane: Mapping[str, Any]) -> list[str]:
    keys: list[str] = [*CURRENT_LIVE_QUALIFIED_LANES, *NEAR_MISS_INCUBATOR_LANES, *PAPER_ONLY_REVIEW_LANES]
    keys.extend(str(key) for key in evidence_by_lane)
    return list(dict.fromkeys(keys))


def _candidate_preview(
    *,
    lane_key: str,
    evidence: Mapping[str, Any],
    log_dir: Path,
    current_fresh_lane: str,
) -> dict[str, Any]:
    symbol, timeframe, direction, entry_mode = _lane_parts(lane_key)
    sample_count = _int_or_none(evidence.get("sample_count") or evidence.get("samples"))
    win_rate_pct = _float_or_none(evidence.get("win_rate_pct"))
    avg_pnl_pct = _float_or_none(evidence.get("avg_pnl_pct"))
    total_pnl_pct = _float_or_none(evidence.get("total_pnl_pct"))
    outcome_stats = _outcome_stats(log_dir, lane_key=lane_key)
    category = _watch_category(lane_key=lane_key, evidence=evidence, sample_count=sample_count, win_rate_pct=win_rate_pct, avg_pnl_pct=avg_pnl_pct)
    risk_contract = build_exact_lane_risk_contract_status(lane_key=lane_key)
    blockers = _blockers(
        category=category,
        sample_count=sample_count,
        win_rate_pct=win_rate_pct,
        avg_pnl_pct=avg_pnl_pct,
        risk_contract=risk_contract,
    )
    return {
        "lane_key": lane_key,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "watch_category": category,
        "sample_count": sample_count or 0,
        "win_rate_pct": win_rate_pct,
        "avg_pnl_pct": avg_pnl_pct,
        "total_pnl_pct": total_pnl_pct,
        "fill_rate_pct": outcome_stats.get("fill_rate_pct"),
        "stop_rate_pct": outcome_stats.get("stop_rate_pct"),
        "freshness_status": "CURRENT_FRESH_CANDIDATE" if lane_key == current_fresh_lane else "NO_CURRENT_FRESH_CANDIDATE",
        "source_chain": list(evidence.get("_source_chain") or []),
        "evidence_files_used": list(evidence.get("_source_chain") or []),
        "risk_contract_compatibility_preview": {
            "exact_contract_found": risk_contract.get("exact_contract_found") is True,
            "risk_contract_valid": risk_contract.get("risk_contract_valid") is True,
            "blocked_by": list(risk_contract.get("blocked_by") or []),
        },
        "blockers": blockers,
        "recommended_lab_action": _recommended_action(lane_key=lane_key, category=category, blockers=blockers, avg_pnl_pct=avg_pnl_pct, sample_count=sample_count),
        "live_allowed": False,
        "final_command_available": False,
        "submit_allowed": False,
        "real_order_forbidden": True,
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "binance_order_endpoint_called": False,
        "binance_test_order_endpoint_called": False,
    }


def _betrayal_previews(log_dir: Path) -> list[dict[str, Any]]:
    status = build_betrayal_paper_outcome_status(log_dir=log_dir)
    rows = status.get("identity_summaries") if isinstance(status.get("identity_summaries"), list) else []
    previews: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        lane_key = build_lane_key(
            symbol=row.get("symbol") or "BTCUSDT",
            timeframe=row.get("timeframe"),
            direction=row.get("direction"),
            entry_mode=row.get("entry_mode") or PREFERRED_ENTRY_MODE,
        )
        sample_count = _int_or_none(row.get("true_paper_outcomes_count")) or 0
        win_rate_pct = _float_or_none(row.get("paper_win_rate_pct"))
        avg_pnl_pct = _float_or_none(row.get("paper_avg_pnl_pct"))
        total_pnl_pct = _float_or_none(row.get("paper_total_pnl_pct"))
        risk_contract = build_exact_lane_risk_contract_status(lane_key=lane_key)
        stale_shadow = _stale_shadow_outcomes_seen(log_dir, lane_key=lane_key)
        decision = _betrayal_decision(
            sample_count=sample_count,
            win_rate_pct=win_rate_pct,
            avg_pnl_pct=avg_pnl_pct,
            stale_shadow=stale_shadow,
            risk_contract=risk_contract,
        )
        previews.append(
            {
                "lane_key": lane_key,
                "symbol": row.get("symbol") or "BTCUSDT",
                "timeframe": row.get("timeframe"),
                "direction": row.get("direction"),
                "entry_mode": row.get("entry_mode") or PREFERRED_ENTRY_MODE,
                "watch_category": BETRAYAL_INVERSE_PREVIEW,
                "original_lane_evidence": {},
                "inverse_betrayal_evidence": dict(row),
                "sample_count": sample_count,
                "win_rate_pct": win_rate_pct,
                "avg_pnl_pct": avg_pnl_pct,
                "total_pnl_pct": total_pnl_pct,
                "original_vs_inverse_delta": None,
                "signal_origin_source_chain": [status.get("ledger_path")],
                "stale_shadow_outcome_check": "STALE_SHADOW_OUTCOME_SEEN" if stale_shadow else "NO_STALE_SHADOW_OUTCOME_SEEN",
                "risk_contract_compatibility_preview": {
                    "exact_contract_found": risk_contract.get("exact_contract_found") is True,
                    "risk_contract_valid": risk_contract.get("risk_contract_valid") is True,
                    "blocked_by": list(risk_contract.get("blocked_by") or []),
                },
                "betrayal_gate_decision": decision,
                "recommended_lab_action": BETRAYAL_LAB_REVIEW if decision != BETRAYAL_REJECTED else BLOCKED_POLICY,
                "live_allowed": False,
                "final_command_available": False,
                "submit_allowed": False,
                "real_order_forbidden": True,
            }
        )
    return previews


def _watch_category(
    *,
    lane_key: str,
    evidence: Mapping[str, Any],
    sample_count: int | None,
    win_rate_pct: float | None,
    avg_pnl_pct: float | None,
) -> str:
    raw = evidence.get("watch_category") or evidence.get("live_qualification_class")
    if raw in {LIVE_QUALIFIED, NEAR_MISS_INCUBATOR, PAPER_ONLY}:
        return str(raw)
    if sample_count is None or sample_count < 30 or win_rate_pct is None or avg_pnl_pct is None:
        return BLOCKED
    if avg_pnl_pct <= 0.0:
        return BLOCKED
    if win_rate_pct >= 55.0:
        return LIVE_QUALIFIED
    if win_rate_pct >= 53.0 or lane_key in NEAR_MISS_INCUBATOR_LANES:
        return NEAR_MISS_INCUBATOR
    return PAPER_ONLY


def _blockers(
    *,
    category: str,
    sample_count: int | None,
    win_rate_pct: float | None,
    avg_pnl_pct: float | None,
    risk_contract: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if sample_count is None or sample_count < 30:
        blockers.append("sample_count_below_30_or_missing")
    if win_rate_pct is None:
        blockers.append("win_rate_pct_missing")
    if avg_pnl_pct is None:
        blockers.append("avg_pnl_pct_missing")
    elif avg_pnl_pct <= 0.0:
        blockers.append("avg_pnl_pct_not_positive")
    if category != LIVE_QUALIFIED:
        blockers.append("not_live_qualified_for_tiny_live")
    if risk_contract.get("exact_contract_found") is not True:
        blockers.append("exact_lane_risk_contract_missing")
    elif risk_contract.get("risk_contract_valid") is not True:
        blockers.append("exact_lane_risk_contract_invalid")
    return list(dict.fromkeys(blockers))


def _recommended_action(
    *,
    lane_key: str,
    category: str,
    blockers: list[str],
    avg_pnl_pct: float | None,
    sample_count: int | None,
) -> str:
    if sample_count is None or sample_count < 30:
        return BLOCKED_INSUFFICIENT_EVIDENCE
    if avg_pnl_pct is not None and avg_pnl_pct <= 0.0:
        return BLOCKED_NEGATIVE_PNL
    if category == LIVE_QUALIFIED and lane_key == CURRENT_TINY_LIVE_LANE:
        return KEEP_TINY_LIVE_WAIT
    if category == LIVE_QUALIFIED:
        return EXPANSION_PREVIEW_ONLY
    if category in {NEAR_MISS_INCUBATOR, PAPER_ONLY}:
        return STRATEGY_LAB_REVIEW
    if blockers:
        return BLOCKED_POLICY
    return STRATEGY_LAB_REVIEW


def _betrayal_decision(
    *,
    sample_count: int,
    win_rate_pct: float | None,
    avg_pnl_pct: float | None,
    stale_shadow: bool,
    risk_contract: Mapping[str, Any],
) -> str:
    if sample_count < 30 or win_rate_pct is None or avg_pnl_pct is None:
        return BETRAYAL_BLOCKED_PREVIEW_ONLY
    if win_rate_pct >= 60.0 and avg_pnl_pct > 0.0 and not stale_shadow and risk_contract.get("exact_contract_found") is True:
        return BETRAYAL_PROMOTION_CANDIDATE_FOR_FUTURE_REVIEW
    if avg_pnl_pct <= 0.0:
        return BETRAYAL_REJECTED
    return BETRAYAL_BLOCKED_PREVIEW_ONLY


def _outcome_stats(log_dir: Path, *, lane_key: str) -> dict[str, float | None]:
    symbol, timeframe, direction, entry_mode = _lane_parts(lane_key)
    all_rows = [
        row
        for row in load_outcomes(log_dir)
        if row.symbol == symbol and row.timeframe == timeframe and row.direction == direction and row.entry_mode == entry_mode
    ]
    if not all_rows:
        return {"fill_rate_pct": None, "stop_rate_pct": None}
    filled = [row for row in all_rows if row.fill_status in {"filled", "partial"}]
    stops = [row for row in filled if row.stop_hit]
    return {
        "fill_rate_pct": round((len(filled) / len(all_rows)) * 100.0, 2),
        "stop_rate_pct": round((len(stops) / len(filled)) * 100.0, 2) if filled else None,
    }


def _stale_shadow_outcomes_seen(log_dir: Path, *, lane_key: str) -> bool:
    records = read_recent_ndjson_records(log_dir / "betrayal_shadow_outcomes.ndjson", limit=200)
    return any(str(row.get("lane_key") or "") == lane_key and "stale" in json.dumps(row).lower() for row in records)


def _top_candidates(candidates: list[Mapping[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    ranked = sorted(
        candidates,
        key=lambda row: (
            row.get("watch_category") == LIVE_QUALIFIED,
            _float_or_none(row.get("avg_pnl_pct")) or -999.0,
            _float_or_none(row.get("win_rate_pct")) or -999.0,
            _int_or_none(row.get("sample_count")) or 0,
        ),
        reverse=True,
    )
    return [dict(row) for row in ranked[:limit]]


def _lane_key(row: Mapping[str, Any]) -> str | None:
    raw = row.get("strategy_key") or row.get("lane_key")
    if raw:
        return str(raw)
    if not any(row.get(key) for key in ("symbol", "timeframe", "direction")):
        return None
    return build_lane_key(
        symbol=row.get("symbol") or "BTCUSDT",
        timeframe=row.get("timeframe"),
        direction=row.get("direction"),
        entry_mode=row.get("entry_mode") or PREFERRED_ENTRY_MODE,
    )


def _lane_parts(lane_key: str) -> tuple[str, str, str, str]:
    parts = [*str(lane_key or "").split("|"), "", "", "", ""]
    return parts[0], parts[1], parts[2], parts[3] or PREFERRED_ENTRY_MODE


def _float_or_none(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _sanitize(payload: Any) -> Any:
    if isinstance(payload, dict):
        sanitized = {str(key): _sanitize(value) for key, value in payload.items()}
        for key in (
            "live_execution_enabled",
            "allow_live_orders",
            "order_placed",
            "real_order_placed",
            "execution_attempted",
            "submit_allowed",
            "final_command_available",
            "binance_order_endpoint_called",
            "binance_test_order_endpoint_called",
            "leverage_change_called",
            "margin_change_called",
            "secrets_shown",
            "secret_values_in_output",
            "kill_switch_disabled",
            "global_live_flags_changed",
        ):
            if key in sanitized:
                sanitized[key] = False
        if "real_order_forbidden" in sanitized:
            sanitized["real_order_forbidden"] = True
        return sanitized
    if isinstance(payload, list):
        return [_sanitize(item) for item in payload]
    return payload


def _main() -> int:
    parser = argparse.ArgumentParser(prog="python -m src.app.hammer_radar.operator.strategy_lab_preview")
    parser.add_argument("--log-dir", default=None)
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()
    payload = build_strategy_lab_preview(log_dir=args.log_dir, write=not args.no_write)
    print(format_strategy_lab_preview_json(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
