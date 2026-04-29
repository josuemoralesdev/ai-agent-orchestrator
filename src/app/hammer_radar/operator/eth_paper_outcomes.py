"""ETHUSDT paper-only outcome tracker for Hammer Radar.

R34 measures archived ETHUSDT paper candidates over time. It never creates live
trade tickets, places orders, or changes BTCUSDT-only live readiness.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.eth_paper_candidates import load_eth_candidates

LIVE_EXECUTION_ENABLED = False
ORDER_PLACED = False
SOURCE = "ethusdt_paper_outcome_tracker"
OUTCOMES_FILENAME = "ethusdt_paper_outcomes.ndjson"
SYMBOL = "ETHUSDT"
ROTATION_PAIR = "ETHBTC"
WARNING = "ETHUSDT paper-only; BTCUSDT remains the only live-readiness symbol."


def build_eth_paper_outcome(
    *,
    candidate_id: str | None = None,
    write: bool = False,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    candidate = _select_candidate(candidate_id=candidate_id, log_dir=resolved_log_dir)
    if candidate is None:
        return {
            "live_execution_enabled": LIVE_EXECUTION_ENABLED,
            "order_placed": ORDER_PLACED,
            "symbol": SYMBOL,
            "rotation_pair": ROTATION_PAIR,
            "candidate_id": candidate_id,
            "outcome_created": False,
            "outcome": None,
            "outcome_status": "ETH_PAPER_NO_DATA",
            "outcome_reason": "No ETHUSDT paper candidates are archived yet.",
            "write": bool(write),
        }

    outcome = build_outcome_from_candidate(candidate)
    if write:
        append_eth_paper_outcome(outcome, log_dir=resolved_log_dir)
    outcome["write"] = bool(write)
    outcome["outcome_created"] = True
    return outcome


def build_outcome_from_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    created_at = datetime.now(UTC).isoformat()
    direction = str(candidate.get("direction") or "unknown")
    entry_price, stop_price, take_profit_price = _levels(direction=direction, last_price=candidate.get("last_price"))
    outcome_status, outcome_reason = _outcome_status(candidate, entry_price=entry_price)
    return {
        "outcome_id": _outcome_id(candidate_id=str(candidate.get("candidate_id") or ""), created_at=created_at),
        "created_at": created_at,
        "source": SOURCE,
        "candidate_id": candidate.get("candidate_id"),
        "candidate_created_at": candidate.get("created_at"),
        "symbol": SYMBOL,
        "rotation_pair": ROTATION_PAIR,
        "ethbtc_rotation_state": candidate.get("ethbtc_rotation_state") or "UNKNOWN",
        "candidate_direction": direction,
        "candidate_tier": candidate.get("tier"),
        "paper_candidate_status": candidate.get("paper_candidate_status"),
        "candidate_score": candidate.get("score"),
        "entry_price": entry_price,
        "stop_price": stop_price,
        "take_profit_price": take_profit_price,
        "outcome_status": outcome_status,
        "outcome_reason": outcome_reason,
        "pnl_pct": None,
        "pnl_usd": None,
        "comparison_to_rotation": _comparison_to_rotation(direction, str(candidate.get("ethbtc_rotation_state") or "UNKNOWN")),
        "market_data_status": candidate.get("market_data_status") or "MARKET_DATA_UNAVAILABLE",
        "live_eligible_symbol": False,
        "paper_watch_enabled": True,
        "watch_only": True,
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
    }


def load_eth_paper_outcomes(
    *,
    limit: int = 50,
    status: str | None = None,
    candidate_id: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = _outcomes_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if status is not None and record.get("outcome_status") != status:
                continue
            if candidate_id is not None and record.get("candidate_id") != candidate_id:
                continue
            records.append(record)
    records = list(reversed(records))
    if limit > 0:
        return records[:limit]
    return records


def append_eth_paper_outcome(record: dict[str, Any], *, log_dir: str | Path | None = None) -> None:
    path = _outcomes_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    to_write = dict(record)
    to_write.pop("write", None)
    to_write.pop("outcome_created", None)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(to_write, sort_keys=True) + "\n")


def build_eth_paper_outcomes_payload(
    *,
    limit: int = 50,
    status: str | None = None,
    candidate_id: str | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    records = load_eth_paper_outcomes(limit=limit, status=status, candidate_id=candidate_id, log_dir=log_dir)
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "symbol": SYMBOL,
        "rotation_pair": ROTATION_PAIR,
        "outcomes": records,
        "summary": _summary(records),
    }


def build_eth_paper_outcome_summary(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    records = load_eth_paper_outcomes(limit=0, log_dir=log_dir)
    candidates = load_eth_candidates(limit=0, log_dir=log_dir)
    latest = records[0] if records else None
    counts = _summary(records)
    current_rotation_state = _current_rotation_state(latest=latest, candidates=candidates)
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "symbol": SYMBOL,
        "rotation_pair": ROTATION_PAIR,
        "total_outcomes": len(records),
        "open_count": counts["open_count"],
        "win_count": counts["win_count"],
        "loss_count": counts["loss_count"],
        "unresolved_count": counts["unresolved_count"],
        "no_data_count": counts["no_data_count"],
        "latest_outcome": latest,
        "current_rotation_state": current_rotation_state,
        "next_required_action": _next_required_action(records=records, candidates=candidates),
        "warning": WARNING,
    }


def build_eth_paper_outcome_text(
    *,
    candidate_id: str | None = None,
    write: bool = False,
    log_dir: str | Path | None = None,
) -> str:
    record = build_eth_paper_outcome(candidate_id=candidate_id, write=write, log_dir=log_dir)
    lines = [
        "HAMMER RADAR ETHUSDT PAPER OUTCOME",
        "live_execution_enabled: false",
        "order_placed: false",
        f"symbol: {record['symbol']}",
        f"rotation_pair: {record['rotation_pair']}",
        f"candidate_id: {record.get('candidate_id')}",
        f"outcome_status: {record.get('outcome_status')}",
        f"write: {str(record.get('write') is True).lower()}",
    ]
    if record.get("outcome_created"):
        lines.extend(
            [
                f"candidate_direction: {record.get('candidate_direction')}",
                f"entry_price: {record.get('entry_price')}",
                f"stop_price: {record.get('stop_price')}",
                f"take_profit_price: {record.get('take_profit_price')}",
                f"reason: {record.get('outcome_reason')}",
            ]
        )
    else:
        lines.append(f"reason: {record.get('outcome_reason')}")
    return "\n".join(lines)


def build_eth_paper_outcomes_text(
    *,
    limit: int = 50,
    status: str | None = None,
    candidate_id: str | None = None,
    log_dir: str | Path | None = None,
) -> str:
    payload = build_eth_paper_outcomes_payload(
        limit=limit,
        status=status,
        candidate_id=candidate_id,
        log_dir=log_dir,
    )
    lines = [
        "HAMMER RADAR ETHUSDT PAPER OUTCOMES",
        "live_execution_enabled: false",
        "order_placed: false",
        f"records: {len(payload['outcomes'])}",
    ]
    if not payload["outcomes"]:
        return "\n".join([*lines, "no ETHUSDT paper outcomes"])
    for record in payload["outcomes"]:
        lines.append(
            f"{record.get('created_at')} | {record.get('outcome_id')} | "
            f"{record.get('candidate_id')} | {record.get('outcome_status')} | "
            f"direction={record.get('candidate_direction')}"
        )
    return "\n".join(lines)


def build_eth_paper_outcome_summary_text(*, log_dir: str | Path | None = None) -> str:
    summary = build_eth_paper_outcome_summary(log_dir=log_dir)
    return "\n".join(
        [
            "HAMMER RADAR ETHUSDT PAPER OUTCOME SUMMARY",
            "live_execution_enabled: false",
            "order_placed: false",
            f"symbol: {summary['symbol']}",
            f"rotation_pair: {summary['rotation_pair']}",
            f"total_outcomes: {summary['total_outcomes']}",
            f"open_count: {summary['open_count']}",
            f"win_count: {summary['win_count']}",
            f"loss_count: {summary['loss_count']}",
            f"unresolved_count: {summary['unresolved_count']}",
            f"no_data_count: {summary['no_data_count']}",
            f"current_rotation_state: {summary['current_rotation_state']}",
            f"next_required_action: {summary['next_required_action']}",
            f"warning: {summary['warning']}",
        ]
    )


def _select_candidate(*, candidate_id: str | None, log_dir: Path) -> dict[str, Any] | None:
    candidates = load_eth_candidates(limit=0, log_dir=log_dir)
    if candidate_id is None:
        return candidates[0] if candidates else None
    return next((candidate for candidate in candidates if candidate.get("candidate_id") == candidate_id), None)


def _outcome_status(candidate: dict[str, Any], *, entry_price: float | None) -> tuple[str, str]:
    paper_status = candidate.get("paper_candidate_status")
    tier = candidate.get("tier")
    if paper_status == "INSUFFICIENT_DATA" or tier == "ETH_INSUFFICIENT_DATA":
        return "ETH_PAPER_NO_DATA", "Candidate lacks sufficient ETHUSDT market data; no win/loss is fabricated."
    if paper_status in {"NO_SIGNAL", "WATCH_ONLY_CONTEXT"} or tier in {"ETH_NO_SIGNAL", "ETH_WATCH_ONLY"}:
        return "ETH_PAPER_NO_SIGNAL", "Candidate is watch-only or no-signal context; no win/loss is fabricated."
    if paper_status == "PAPER_CANDIDATE" or tier == "ETH_PAPER_CANDIDATE":
        if entry_price is None:
            return "ETH_PAPER_NO_DATA", "Candidate has no entry price source; no paper outcome can be measured."
        return "ETH_PAPER_UNRESOLVED", "Deterministic levels were created, but candle path is unavailable."
    return "ETH_PAPER_NO_DATA", "Candidate status is not measurable by R34 outcome tracker."


def _levels(*, direction: str, last_price: object) -> tuple[float | None, float | None, float | None]:
    entry = _float_or_none(last_price)
    if entry is None or direction not in {"long", "short"}:
        return None, None, None
    if direction == "long":
        return entry, round(entry * 0.995, 8), round(entry * 1.005, 8)
    return entry, round(entry * 1.005, 8), round(entry * 0.995, 8)


def _comparison_to_rotation(direction: str, rotation_state: str) -> str:
    if rotation_state == "UNKNOWN" or direction not in {"long", "short"}:
        return "unknown"
    if direction == "long" and rotation_state == "ETH_LEADING_BTC":
        return "aligned_with_ethbtc"
    if direction == "short" and rotation_state == "ETH_LAGGING_BTC":
        return "aligned_with_ethbtc"
    return "contradicted_ethbtc"


def _summary(records: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "open_count": sum(1 for record in records if record.get("outcome_status") == "ETH_PAPER_OPEN"),
        "win_count": sum(1 for record in records if record.get("outcome_status") == "ETH_PAPER_WIN"),
        "loss_count": sum(1 for record in records if record.get("outcome_status") == "ETH_PAPER_LOSS"),
        "unresolved_count": sum(1 for record in records if record.get("outcome_status") == "ETH_PAPER_UNRESOLVED"),
        "no_data_count": sum(
            1
            for record in records
            if record.get("outcome_status") in {"ETH_PAPER_NO_DATA", "ETH_PAPER_NO_SIGNAL"}
        ),
    }


def _current_rotation_state(*, latest: dict[str, Any] | None, candidates: list[dict[str, Any]]) -> str:
    if latest is not None:
        return str(latest.get("ethbtc_rotation_state") or "UNKNOWN")
    if candidates:
        return str(candidates[0].get("ethbtc_rotation_state") or "UNKNOWN")
    return "UNKNOWN"


def _next_required_action(*, records: list[dict[str, Any]], candidates: list[dict[str, Any]]) -> str:
    if not candidates:
        return "Archive an ETHUSDT paper candidate before tracking paper outcomes."
    if not records:
        return "Preview or archive the latest ETHUSDT paper outcome. Keep ETHUSDT paper-only."
    return "Review ETHUSDT paper outcome history. BTCUSDT remains the only live-readiness symbol."


def _float_or_none(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _outcome_id(*, candidate_id: str, created_at: str) -> str:
    digest = hashlib.sha256(f"{SOURCE}|{candidate_id}|{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"ethpo_{digest}"


def _outcomes_path(log_dir: Path) -> Path:
    return log_dir / OUTCOMES_FILENAME
