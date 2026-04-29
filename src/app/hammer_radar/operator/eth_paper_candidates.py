"""ETHUSDT paper-only candidate engine for Hammer Radar.

R33 creates ETHUSDT paper/watch context only. It never creates live tickets,
places orders, or changes BTCUSDT-only live readiness.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.market_intelligence import (
    build_market_intelligence_summary,
    evaluate_ethbtc_rotation,
)

LIVE_EXECUTION_ENABLED = False
ORDER_PLACED = False
SOURCE = "ethusdt_paper_candidate_engine"
CANDIDATES_FILENAME = "ethusdt_paper_candidates.ndjson"
SYMBOL = "ETHUSDT"
ROTATION_PAIR = "ETHBTC"
WARNING = "ETHUSDT paper-only; BTCUSDT remains the only live-readiness symbol."


def build_eth_paper_candidate(
    *,
    use_network: bool = False,
    write: bool = False,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    market = build_market_intelligence_summary(use_network=use_network, write=False, limit=0, log_dir=resolved_log_dir)
    rotation = evaluate_ethbtc_rotation(use_network=use_network, log_dir=resolved_log_dir)
    eth_record = next((record for record in market.get("symbols", []) if record.get("symbol") == SYMBOL), None)
    candidate = _candidate_from_context(eth_record, rotation=rotation, market_status=market.get("market_data_status"))
    if write:
        append_eth_candidate(candidate, log_dir=resolved_log_dir)
    candidate["write"] = bool(write)
    return candidate


def load_eth_candidates(
    *,
    limit: int = 50,
    status: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = _candidates_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if status is not None and record.get("paper_candidate_status") != status and record.get("tier") != status:
                continue
            records.append(record)
    records = list(reversed(records))
    if limit > 0:
        return records[:limit]
    return records


def append_eth_candidate(record: dict[str, Any], *, log_dir: str | Path | None = None) -> None:
    path = _candidates_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    to_write = dict(record)
    to_write.pop("write", None)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(to_write, sort_keys=True) + "\n")


def build_eth_candidates_payload(
    *,
    limit: int = 50,
    status: str | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    records = load_eth_candidates(limit=limit, status=status, log_dir=log_dir)
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "symbol": SYMBOL,
        "rotation_pair": ROTATION_PAIR,
        "candidates": records,
        "summary": _summary(records),
    }


def build_eth_paper_summary(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    records = load_eth_candidates(limit=0, log_dir=log_dir)
    latest = records[0] if records else None
    current = build_eth_paper_candidate(use_network=False, write=False, log_dir=log_dir)
    counts = _summary(records)
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "symbol": SYMBOL,
        "rotation_pair": ROTATION_PAIR,
        "total_candidates": len(records),
        "latest_candidate": latest,
        "paper_candidate_count": counts["paper_candidate_count"],
        "watch_only_count": counts["watch_only_count"],
        "insufficient_data_count": counts["insufficient_data_count"],
        "current_rotation_state": current["ethbtc_rotation_state"],
        "next_required_action": _next_required_action(current),
        "warning": WARNING,
    }


def build_eth_paper_candidate_text(
    *,
    use_network: bool = False,
    write: bool = False,
    log_dir: str | Path | None = None,
) -> str:
    record = build_eth_paper_candidate(use_network=use_network, write=write, log_dir=log_dir)
    return "\n".join(
        [
            "HAMMER RADAR ETHUSDT PAPER CANDIDATE",
            "live_execution_enabled: false",
            "order_placed: false",
            f"symbol: {record['symbol']}",
            f"rotation_pair: {record['rotation_pair']}",
            f"ethbtc_rotation_state: {record['ethbtc_rotation_state']}",
            f"paper_candidate_status: {record['paper_candidate_status']}",
            f"tier: {record['tier']}",
            f"direction: {record['direction']}",
            f"score: {record['score']}",
            f"write: {str(record['write']).lower()}",
            f"reason: {record['reason']}",
        ]
    )


def build_eth_candidates_text(
    *,
    limit: int = 50,
    status: str | None = None,
    log_dir: str | Path | None = None,
) -> str:
    payload = build_eth_candidates_payload(limit=limit, status=status, log_dir=log_dir)
    lines = [
        "HAMMER RADAR ETHUSDT PAPER CANDIDATES",
        "live_execution_enabled: false",
        "order_placed: false",
        f"records: {len(payload['candidates'])}",
    ]
    if not payload["candidates"]:
        return "\n".join([*lines, "no ETHUSDT paper candidates"])
    for record in payload["candidates"]:
        lines.append(
            f"{record.get('created_at')} | {record.get('candidate_id')} | "
            f"{record.get('paper_candidate_status')} | {record.get('direction')} | score={record.get('score')}"
        )
    return "\n".join(lines)


def build_eth_paper_summary_text(*, log_dir: str | Path | None = None) -> str:
    summary = build_eth_paper_summary(log_dir=log_dir)
    return "\n".join(
        [
            "HAMMER RADAR ETHUSDT PAPER SUMMARY",
            "live_execution_enabled: false",
            "order_placed: false",
            f"symbol: {summary['symbol']}",
            f"rotation_pair: {summary['rotation_pair']}",
            f"total_candidates: {summary['total_candidates']}",
            f"paper_candidate_count: {summary['paper_candidate_count']}",
            f"watch_only_count: {summary['watch_only_count']}",
            f"insufficient_data_count: {summary['insufficient_data_count']}",
            f"current_rotation_state: {summary['current_rotation_state']}",
            f"next_required_action: {summary['next_required_action']}",
            f"warning: {summary['warning']}",
        ]
    )


def _candidate_from_context(
    eth_record: dict[str, Any] | None,
    *,
    rotation: dict[str, Any],
    market_status: object,
) -> dict[str, Any]:
    created_at = datetime.now(UTC).isoformat()
    eth_status = str((eth_record or {}).get("market_data_status") or market_status or "MARKET_DATA_UNAVAILABLE")
    change = _float_or_none((eth_record or {}).get("price_change_percent_24h"))
    rotation_state = str(rotation.get("rotation_state") or "UNKNOWN")
    direction, tier, paper_status, reason = _classify_candidate(
        change=change,
        rotation_state=rotation_state,
        market_data_status=eth_status,
    )
    score = _candidate_score(eth_record, change=change, rotation_state=rotation_state, paper_status=paper_status)
    return {
        "candidate_id": _candidate_id(created_at=created_at),
        "created_at": created_at,
        "source": SOURCE,
        "symbol": SYMBOL,
        "rotation_pair": ROTATION_PAIR,
        "ethbtc_rotation_state": rotation_state,
        "ethbtc_change_percent_24h": rotation.get("ethbtc_change_percent_24h"),
        "market_data_status": eth_status,
        "direction": direction,
        "timeframe": "paper_context",
        "score": score,
        "tier": tier,
        "paper_candidate_status": paper_status,
        "reason": reason,
        "market_intelligence_score": (eth_record or {}).get("market_intelligence_score"),
        "momentum_score": (eth_record or {}).get("momentum_score"),
        "liquidity_score": (eth_record or {}).get("liquidity_score"),
        "last_price": (eth_record or {}).get("last_price"),
        "price_change_percent_24h": change,
        "quote_volume_24h": (eth_record or {}).get("quote_volume_24h"),
        "suggested_position_usd": None,
        "suggested_leverage": 0,
        "live_eligible_symbol": False,
        "paper_watch_enabled": True,
        "watch_only": True,
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
    }


def _classify_candidate(
    *,
    change: float | None,
    rotation_state: str,
    market_data_status: str,
) -> tuple[str, str, str, str]:
    if change is None or market_data_status not in {"OK", "PARTIAL"}:
        return (
            "unknown",
            "ETH_INSUFFICIENT_DATA",
            "INSUFFICIENT_DATA",
            "ETHUSDT market data unavailable; no paper signal is fabricated.",
        )
    if change >= 2.0 and rotation_state == "ETH_LEADING_BTC":
        return (
            "long",
            "ETH_PAPER_CANDIDATE",
            "PAPER_CANDIDATE",
            "ETHUSDT momentum is positive and ETHBTC shows ETH leading BTC; paper-only long watch context.",
        )
    if change <= -2.0 and rotation_state == "ETH_LAGGING_BTC":
        return (
            "short",
            "ETH_WATCH_ONLY",
            "WATCH_ONLY_CONTEXT",
            "ETHUSDT momentum is negative and ETHBTC lags BTC; paper-only short watch context.",
        )
    if change > 0:
        return (
            "neutral",
            "ETH_WATCH_ONLY",
            "WATCH_ONLY_CONTEXT",
            "ETHUSDT momentum is positive, but ETHBTC rotation is not strongly leading; watch-only context.",
        )
    return (
        "neutral",
        "ETH_NO_SIGNAL",
        "NO_SIGNAL",
        "ETHUSDT does not meet R33 paper candidate thresholds.",
    )


def _candidate_score(
    eth_record: dict[str, Any] | None,
    *,
    change: float | None,
    rotation_state: str,
    paper_status: str,
) -> int:
    score = int((eth_record or {}).get("market_intelligence_score") or 0)
    if paper_status == "PAPER_CANDIDATE":
        score += 10
    if rotation_state == "ETH_LEADING_BTC":
        score += 5
    if rotation_state == "ETH_LAGGING_BTC":
        score -= 5
    if change is None:
        score = min(score, 40)
    return max(0, min(100, score))


def _summary(records: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "paper_candidate_count": sum(1 for record in records if record.get("paper_candidate_status") == "PAPER_CANDIDATE"),
        "watch_only_count": sum(1 for record in records if record.get("paper_candidate_status") == "WATCH_ONLY_CONTEXT"),
        "insufficient_data_count": sum(1 for record in records if record.get("paper_candidate_status") == "INSUFFICIENT_DATA"),
    }


def _next_required_action(current: dict[str, Any]) -> str:
    if current.get("paper_candidate_status") == "PAPER_CANDIDATE":
        return "Review ETHUSDT as paper-only context. Do not create a live ticket."
    return "Wait for stronger ETHUSDT data and ETHBTC rotation confirmation. BTCUSDT remains the only live-readiness symbol."


def _float_or_none(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _candidate_id(*, created_at: str) -> str:
    digest = hashlib.sha256(f"{SOURCE}|{SYMBOL}|{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"ethpc_{digest}"


def _candidates_path(log_dir: Path) -> Path:
    return log_dir / CANDIDATES_FILENAME
