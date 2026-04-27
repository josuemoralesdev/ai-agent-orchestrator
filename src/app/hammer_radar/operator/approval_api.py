"""Local approval-intent API for Hammer Radar operator candidates.

This module records human intent only. It does not place orders, import exchange
clients, or enable live execution.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.inspect import (
    LIVE_DECISION_ELIGIBLE,
    LIVE_DECISION_FORBIDDEN,
    LiveCandidateCheck,
    build_live_candidate_snapshot,
)

SERVICE_NAME = "hammer_radar_approval_api"
DECISIONS_FILENAME = "manual_decisions.ndjson"
LIVE_EXECUTION_ENABLED = False
ORDER_PLACED = False
DEFAULT_MAX_POSITION_USD = 44.0
DEFAULT_MAX_LEVERAGE = 3.0

DecisionValue = Literal["approve_manual_live", "reject", "paper_only", "watch"]

app = FastAPI(title="Hammer Radar Approval API")


class DecisionRequest(BaseModel):
    signal_id: str = Field(min_length=1)
    decision: DecisionValue
    operator: str = Field(min_length=1)
    notes: str = ""
    intended_position_usd: float | None = None
    intended_leverage: float | None = None
    override_reason: str | None = None


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "service": SERVICE_NAME,
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
    }


@app.get("/candidates")
def candidates(
    limit: int = Query(default=10, ge=0),
    since_hours: int = Query(default=24, ge=0),
    fresh_minutes: int = Query(default=30, ge=0),
    max_position_usd: float = Query(default=DEFAULT_MAX_POSITION_USD, gt=0),
    max_risk_usd: float = Query(default=5.0, gt=0),
    max_leverage: float = Query(default=DEFAULT_MAX_LEVERAGE, ge=0),
    allow_short: bool = False,
    allow_oversold: bool = False,
    allow_trigger_flags: bool = False,
    latest_only: bool = False,
    symbol: str | None = None,
) -> dict:
    snapshot = build_live_candidate_snapshot(
        limit=limit,
        since_hours=since_hours,
        fresh_minutes=fresh_minutes,
        max_position_usd=max_position_usd,
        max_risk_usd=max_risk_usd,
        max_leverage=max_leverage,
        allow_short=allow_short,
        allow_oversold=allow_oversold,
        allow_trigger_flags=allow_trigger_flags,
        latest_only=latest_only,
    )
    return {
        "archive_log_dir": str(snapshot["archive_log_dir"]),
        "generated_at": snapshot["generated_at"].isoformat(),
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "candidates": [_candidate_snapshot(check) for check in snapshot["checks"]],
    }


@app.post("/decisions")
def create_decision(request: DecisionRequest) -> dict:
    log_dir = get_log_dir(use_env=True)
    candidate = _current_candidate_by_signal_id(request.signal_id)
    _validate_decision_request(request, candidate)
    record = {
        "decision_id": uuid4().hex,
        "created_at": datetime.now(UTC).isoformat(),
        "archive_log_dir": str(log_dir),
        "signal_id": request.signal_id,
        "decision": request.decision,
        "operator": request.operator,
        "notes": request.notes,
        "intended_position_usd": request.intended_position_usd,
        "intended_leverage": request.intended_leverage,
        "override_reason": request.override_reason,
        "candidate_snapshot": candidate,
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "source": "approval_api",
    }
    _append_decision(record, log_dir=log_dir)
    return record


@app.get("/decisions")
def decisions(limit: int = Query(default=50, ge=0), signal_id: str | None = None) -> dict:
    records = load_decisions(limit=limit, signal_id=signal_id, log_dir=get_log_dir(use_env=True))
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "decisions": records,
    }


@app.get("/decisions/{decision_id}")
def decision_by_id(decision_id: str) -> dict:
    for record in load_decisions(limit=0, log_dir=get_log_dir(use_env=True)):
        if record.get("decision_id") == decision_id:
            record = dict(record)
            record["live_execution_enabled"] = LIVE_EXECUTION_ENABLED
            record["order_placed"] = ORDER_PLACED
            return record
    raise HTTPException(status_code=404, detail="decision not found")


def build_decisions_text(
    *,
    limit: int = 50,
    signal_id: str | None = None,
    log_dir: str | Path | None = None,
) -> str:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    records = load_decisions(limit=limit, signal_id=signal_id, log_dir=resolved_log_dir)
    lines = [
        "HAMMER RADAR MANUAL DECISIONS",
        f"archive_log_dir: {resolved_log_dir}",
        "live_execution_enabled: false",
        "order_placed: false",
    ]
    if not records:
        return "\n".join([*lines, "no manual decisions"])
    for record in records:
        lines.append(
            f"{record.get('created_at')} | {record.get('decision_id')} | signal={record.get('signal_id')} | "
            f"decision={record.get('decision')} | operator={record.get('operator')} | notes={record.get('notes', '')}"
        )
    return "\n".join(lines)


def load_decisions(
    *,
    limit: int = 50,
    signal_id: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict]:
    path = _decisions_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if signal_id is not None and record.get("signal_id") != signal_id:
                continue
            records.append(record)
    records = list(reversed(records))
    if limit > 0:
        return records[:limit]
    return records


def _current_candidate_by_signal_id(signal_id: str) -> dict | None:
    snapshot = build_live_candidate_snapshot(
        limit=1000,
        since_hours=24,
        fresh_minutes=30,
        max_position_usd=DEFAULT_MAX_POSITION_USD,
        max_risk_usd=5.0,
        max_leverage=DEFAULT_MAX_LEVERAGE,
    )
    for check in snapshot["checks"]:
        candidate = _candidate_snapshot(check)
        if candidate["signal_id"] == signal_id:
            return candidate
    return None


def _validate_decision_request(request: DecisionRequest, candidate: dict | None) -> None:
    if request.decision != "approve_manual_live":
        return
    if candidate is None:
        raise HTTPException(status_code=400, detail="approve_manual_live requires a current candidate")
    if candidate["decision"] == LIVE_DECISION_FORBIDDEN:
        raise HTTPException(status_code=400, detail="FORBIDDEN candidates cannot be approved")
    if candidate["decision"] != LIVE_DECISION_ELIGIBLE and not request.override_reason:
        raise HTTPException(status_code=400, detail="approval requires ELIGIBLE_TINY_LIVE or override_reason")
    if candidate["freshness_status"] == "expired" and not request.override_reason:
        raise HTTPException(status_code=400, detail="expired candidate approval requires override_reason")
    if (
        request.intended_position_usd is not None
        and request.intended_position_usd > DEFAULT_MAX_POSITION_USD
        and not request.override_reason
    ):
        raise HTTPException(status_code=400, detail="intended_position_usd exceeds default max_position_usd")
    if (
        request.intended_leverage is not None
        and request.intended_leverage > DEFAULT_MAX_LEVERAGE
        and not request.override_reason
    ):
        raise HTTPException(status_code=400, detail="intended_leverage exceeds default max_leverage")


def _candidate_snapshot(check: LiveCandidateCheck) -> dict:
    signal = check.candidate.signal
    return {
        "signal_id": signal.signal_id,
        "timestamp": signal.timestamp,
        "symbol": signal.symbol,
        "timeframe": signal.timeframe,
        "direction": signal.direction,
        "decision": check.decision,
        "reason": check.reason,
        "score": check.candidate.score,
        "tier": check.candidate.tier,
        "tradable": signal.tradable,
        "reject_reason": signal.reject_reason,
        "entry": check.entry,
        "stop": check.stop,
        "take_profit": check.take_profit,
        "age_minutes": check.age_minutes,
        "freshness_status": check.freshness_status,
        "risk_distance_pct": check.risk_distance_pct,
        "theoretical_max_position_size_usd": check.theoretical_max_position_usd,
        "capped_max_position_size_usd": check.capped_max_position_usd,
        "suggested_leverage": check.suggested_leverage,
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
    }


def _append_decision(record: dict, *, log_dir: Path) -> None:
    path = _decisions_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def _decisions_path(log_dir: Path) -> Path:
    return log_dir / DECISIONS_FILENAME


def main() -> int:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8015)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
