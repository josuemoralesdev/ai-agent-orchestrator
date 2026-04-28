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
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.binance_readonly import (
    build_binance_exchange_info,
    build_binance_readonly_status,
)
from src.app.hammer_radar.operator.exchange_dry_run import (
    build_current_exchange_dry_run,
    build_exchange_dry_run,
)
from src.app.hammer_radar.operator.live_safety import (
    build_current_live_safety,
    evaluate_live_safety,
)
from src.app.hammer_radar.operator.live_connector_stub import (
    CONNECTOR_MODE,
    load_live_attempts,
    submit_live_order_stub,
)
from src.app.hammer_radar.operator.inspect import (
    LIVE_DECISION_ELIGIBLE,
    LIVE_DECISION_FORBIDDEN,
    LiveCandidateCheck,
    build_live_candidate_snapshot,
)
from src.app.hammer_radar.operator.manual_outcomes import (
    append_manual_outcome,
    load_manual_outcomes,
)
from src.app.hammer_radar.operator.paper_execution import (
    execute_paper_ticket,
    load_paper_executions,
)
from src.app.hammer_radar.operator.readiness import build_readiness_payload
from src.app.hammer_radar.operator.trade_ticket import (
    approve_paper_ticket,
    build_trade_ticket,
    load_trade_ticket_records,
)

SERVICE_NAME = "hammer_radar_approval_api"
DECISIONS_FILENAME = "manual_decisions.ndjson"
LIVE_EXECUTION_ENABLED = False
ORDER_PLACED = False
DEFAULT_MAX_POSITION_USD = 44.0
DEFAULT_MAX_LEVERAGE = 3.0

DecisionValue = Literal["approve_manual_live", "reject", "paper_only", "watch"]
ManualOutcomeResult = Literal["win", "loss", "breakeven", "skipped"]

app = FastAPI(title="Hammer Radar Approval API")


class DecisionRequest(BaseModel):
    signal_id: str = Field(min_length=1)
    decision: DecisionValue
    operator: str = Field(min_length=1)
    notes: str = ""
    intended_position_usd: float | None = None
    intended_leverage: float | None = None
    override_reason: str | None = None


class ManualOutcomeRequest(BaseModel):
    signal_id: str = Field(min_length=1)
    result: ManualOutcomeResult
    entry_price: float | None = None
    exit_price: float | None = None
    position_usd: float | None = None
    leverage: float | None = None
    pnl_usd: float | None = None
    pnl_pct: float | None = None
    notes: str = ""


class ApprovePaperTicketRequest(BaseModel):
    ticket_id: str = Field(min_length=1)
    operator: str = Field(min_length=1)
    notes: str = ""
    ticket_snapshot: dict | None = None


class ExecutePaperTicketRequest(BaseModel):
    ticket_id: str = Field(min_length=1)
    operator: str = Field(min_length=1)
    notes: str = ""


class ExchangeDryRunRequest(BaseModel):
    ticket: dict


class LiveSafetyEvaluateRequest(BaseModel):
    readiness: dict | None = None
    ticket: dict | None = None
    exchange_dry_run: dict | None = None
    decisions: list[dict] | None = None
    paper_executions: list[dict] | None = None
    manual_outcomes: list[dict] | None = None
    config_override: dict | None = None


class LiveConnectorSubmitRequest(BaseModel):
    ticket_id: str = Field(min_length=1)
    operator: str = Field(min_length=1)
    notes: str = ""


@app.get("/", response_class=HTMLResponse)
@app.get("/ui", response_class=HTMLResponse)
def operator_ui() -> str:
    return _operator_ui_html()


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "service": SERVICE_NAME,
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
    }


@app.get("/readiness")
def readiness() -> dict:
    return build_readiness_payload(log_dir=get_log_dir(use_env=True))


@app.get("/trade-ticket")
def trade_ticket(
    signal_id: str | None = None,
    latest_only: bool = True,
    allow_short: bool = False,
    max_position_usd: float = Query(default=DEFAULT_MAX_POSITION_USD, gt=0),
    max_risk_usd: float = Query(default=5.0, gt=0),
    max_leverage: float = Query(default=DEFAULT_MAX_LEVERAGE, gt=0),
    fresh_minutes: int = Query(default=30, ge=0),
) -> dict:
    return build_trade_ticket(
        signal_id=signal_id,
        latest_only=latest_only,
        allow_short=allow_short,
        max_position_usd=max_position_usd,
        max_risk_usd=max_risk_usd,
        max_leverage=max_leverage,
        fresh_minutes=fresh_minutes,
        log_dir=get_log_dir(use_env=True),
    )


@app.post("/trade-ticket/approve-paper")
def approve_paper_trade_ticket(request: ApprovePaperTicketRequest) -> dict:
    try:
        return approve_paper_ticket(
            ticket_id=request.ticket_id,
            operator=request.operator,
            notes=request.notes,
            ticket_snapshot=request.ticket_snapshot,
            log_dir=get_log_dir(use_env=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/trade-tickets")
def trade_tickets(limit: int = Query(default=50, ge=0), ticket_id: str | None = None) -> dict:
    records = load_trade_ticket_records(limit=limit, ticket_id=ticket_id, log_dir=get_log_dir(use_env=True))
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "paper_execution_enabled": False,
        "paper_order_placed": False,
        "trade_tickets": records,
    }


@app.post("/trade-ticket/execute-paper")
def execute_paper_trade_ticket(request: ExecutePaperTicketRequest) -> dict:
    try:
        return execute_paper_ticket(
            ticket_id=request.ticket_id,
            operator=request.operator,
            notes=request.notes,
            log_dir=get_log_dir(use_env=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/paper-executions")
def paper_executions(
    limit: int = Query(default=50, ge=0),
    signal_id: str | None = None,
    status: str | None = None,
) -> dict:
    records = load_paper_executions(
        limit=limit,
        signal_id=signal_id,
        status=status,
        log_dir=get_log_dir(use_env=True),
    )
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "paper_executions": records,
    }


@app.get("/exchange-dry-run")
def exchange_dry_run(
    signal_id: str | None = None,
    allow_short: bool = False,
    max_position_usd: float = Query(default=DEFAULT_MAX_POSITION_USD, gt=0),
    max_risk_usd: float = Query(default=5.0, gt=0),
    max_leverage: float = Query(default=DEFAULT_MAX_LEVERAGE, gt=0),
    fresh_minutes: int = Query(default=30, ge=0),
) -> dict:
    return build_current_exchange_dry_run(
        signal_id=signal_id,
        allow_short=allow_short,
        max_position_usd=max_position_usd,
        max_risk_usd=max_risk_usd,
        max_leverage=max_leverage,
        fresh_minutes=fresh_minutes,
        log_dir=get_log_dir(use_env=True),
    )


@app.post("/exchange-dry-run/from-ticket")
def exchange_dry_run_from_ticket(request: ExchangeDryRunRequest) -> dict:
    return build_exchange_dry_run(request.ticket)


@app.get("/live-safety")
def live_safety(
    signal_id: str | None = None,
    allow_short: bool = False,
    max_position_usd: float = Query(default=DEFAULT_MAX_POSITION_USD, gt=0),
    max_leverage: float = Query(default=DEFAULT_MAX_LEVERAGE, gt=0),
    fresh_minutes: int = Query(default=30, ge=0),
) -> dict:
    return build_current_live_safety(
        signal_id=signal_id,
        allow_short=allow_short,
        max_position_usd=max_position_usd,
        max_leverage=max_leverage,
        fresh_minutes=fresh_minutes,
        log_dir=get_log_dir(use_env=True),
    )


@app.post("/live-safety/evaluate")
def live_safety_evaluate(request: LiveSafetyEvaluateRequest) -> dict:
    return evaluate_live_safety(
        readiness=request.readiness,
        ticket=request.ticket,
        exchange_dry_run=request.exchange_dry_run,
        decisions=request.decisions,
        paper_executions=request.paper_executions,
        manual_outcomes=request.manual_outcomes,
        config_override=request.config_override,
    )


@app.post("/live-connector/stub-submit")
def live_connector_stub_submit(request: LiveConnectorSubmitRequest) -> dict:
    return submit_live_order_stub(
        ticket_id=request.ticket_id,
        operator=request.operator,
        notes=request.notes,
        log_dir=get_log_dir(use_env=True),
    )


@app.get("/live-connector/attempts")
def live_connector_attempts(
    limit: int = Query(default=50, ge=0),
    signal_id: str | None = None,
    ticket_id: str | None = None,
) -> dict:
    records = load_live_attempts(limit=limit, signal_id=signal_id, ticket_id=ticket_id, log_dir=get_log_dir(use_env=True))
    return {
        "connector_mode": CONNECTOR_MODE,
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "live_attempts": records,
    }


@app.get("/binance-readonly/status")
def binance_readonly_status() -> dict:
    return build_binance_readonly_status()


@app.get("/binance-readonly/exchange-info")
def binance_readonly_exchange_info(symbol: str = "BTCUSDT") -> dict:
    return build_binance_exchange_info(symbol=symbol)


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


@app.post("/manual-outcomes")
def create_manual_outcome(request: ManualOutcomeRequest) -> dict:
    record = append_manual_outcome(
        signal_id=request.signal_id,
        result=request.result,
        entry_price=request.entry_price,
        exit_price=request.exit_price,
        position_usd=request.position_usd,
        leverage=request.leverage,
        pnl_usd=request.pnl_usd,
        pnl_pct=request.pnl_pct,
        notes=request.notes,
        log_dir=get_log_dir(use_env=True),
    )
    record["live_execution_enabled"] = LIVE_EXECUTION_ENABLED
    record["order_placed"] = ORDER_PLACED
    return record


@app.get("/manual-outcomes")
def manual_outcomes(limit: int = Query(default=50, ge=0), signal_id: str | None = None) -> dict:
    records = load_manual_outcomes(limit=limit, signal_id=signal_id, log_dir=get_log_dir(use_env=True))
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "manual_outcomes": records,
    }


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


def _operator_ui_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Hammer Radar Approval Console</title>
  <style>
    :root { color-scheme: light; font-family: Arial, sans-serif; background: #f5f6f3; color: #202124; }
    body { margin: 0; }
    header { padding: 18px 24px; background: #18212f; color: white; }
    main { max-width: 1240px; margin: 0 auto; padding: 20px; }
    .banner { background: #fff7ed; border-bottom: 1px solid #fed7aa; color: #7c2d12; padding: 12px 24px; font-weight: 800; }
    .status, .controls, .readiness, .ticket, .exchange-dry-run, .live-safety, .live-connector, .binance-readonly, .paper-execution, .candidate, .decision, .feedback { background: white; border: 1px solid #d9ddd6; border-radius: 8px; padding: 14px; margin-bottom: 14px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 10px; }
    .controls-grid { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; }
    .label { color: #5d675f; font-size: 12px; text-transform: uppercase; }
    .value { font-weight: 700; overflow-wrap: anywhere; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 13px; }
    .danger { color: #9f1d1d; font-weight: 700; }
    .safe { color: #12613a; font-weight: 700; }
    .badge { display: inline-block; border-radius: 999px; padding: 5px 9px; font-size: 12px; font-weight: 800; letter-spacing: 0; }
    .badge-eligible { background: #dcfce7; border: 1px solid #86efac; color: #14532d; }
    .badge-paper { background: #fef3c7; border: 1px solid #fcd34d; color: #78350f; }
    .badge-forbidden { background: #fee2e2; border: 1px solid #fca5a5; color: #7f1d1d; }
    .candidate { border-left: 6px solid #9ca3af; }
    .candidate-eligible { border-left-color: #16a34a; }
    .candidate-paper { border-left-color: #d97706; }
    .candidate-forbidden { border-left-color: #dc2626; }
    .button-row { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
    button { padding: 8px 10px; border: 1px solid #aeb7ad; border-radius: 6px; background: #f2f5ef; cursor: pointer; font-weight: 700; }
    button:hover { background: #e6ece2; }
    button:disabled { color: #7a8178; background: #ecefeb; cursor: not-allowed; }
    .approve { background: #e9f8ee; border-color: #86efac; color: #14532d; }
    .reject { background: #fff1f2; border-color: #fecdd3; color: #7f1d1d; }
    input[type="text"], input[type="number"] { min-width: 180px; padding: 8px; border: 1px solid #b8c0b6; border-radius: 6px; }
    input.notes { width: min(560px, 100%); }
    pre { white-space: pre-wrap; background: #111827; color: #f9fafb; padding: 12px; border-radius: 6px; }
    .success { border-color: #86efac; background: #f0fdf4; color: #14532d; }
    .error { border-color: #fca5a5; background: #fef2f2; color: #7f1d1d; }
    .ready { border-left: 6px solid #16a34a; }
    .not-ready { border-left: 6px solid #dc2626; }
    .proposed { border-left: 6px solid #16a34a; }
    .blocked { border-left: 6px solid #dc2626; }
    .expired { border-left: 6px solid #d97706; }
    .muted { color: #667085; }
    h2 { margin-top: 28px; }
  </style>
</head>
<body>
  <header>
    <h1>Hammer Radar Approval Console</h1>
    <div>Record Decision only. No order placement. live_execution_enabled=false. order_placed=false.</div>
  </header>
  <div class="banner">
    LOCAL PAPER/MANUAL INTENT ONLY | No live order placement. | live_execution_enabled=false | order_placed=false
  </div>
  <main>
    <section class="status">
      <div class="grid">
        <div><div class="label">Health</div><div id="health" class="value">loading</div></div>
        <div><div class="label">live_execution_enabled</div><div id="live" class="value danger">false</div></div>
        <div><div class="label">order_placed</div><div id="order" class="value danger">false</div></div>
        <div><div class="label">Archive</div><div id="archive" class="value">loading</div></div>
        <div><div class="label">Generated</div><div id="generated" class="value">loading</div></div>
      </div>
    </section>

    <h2>Friday Readiness</h2>
    <section id="readiness" class="readiness not-ready">
      <div class="grid">
        <div><div class="label">readiness_status</div><div id="readyStatus" class="value danger">loading</div></div>
        <div><div class="label">allowed_now</div><div id="allowedNow" class="value danger">false</div></div>
        <div><div class="label">fresh eligible count</div><div id="freshEligible" class="value">loading</div></div>
        <div><div class="label">manual outcomes today</div><div id="outcomesToday" class="value">loading</div></div>
        <div><div class="label">losses today</div><div id="lossesToday" class="value">loading</div></div>
        <div><div class="label">pnl today</div><div id="pnlToday" class="value">loading</div></div>
        <div><div class="label">live_execution_enabled</div><div id="readinessLive" class="value danger">false</div></div>
        <div><div class="label">order_placed</div><div id="readinessOrder" class="value danger">false</div></div>
      </div>
      <p><strong>Protocol:</strong> 44 USDT max, 2x preferred, 3x max, isolated margin, max 1 manual tiny-live trade per day, stop after 1 loss or -5 USDT.</p>
      <p id="readinessReason">loading</p>
      <p><strong>Blockers:</strong> <span id="readinessBlockers">loading</span></p>
      <p><strong>Next required action:</strong> <span id="nextAction">loading</span></p>
      <p class="muted">If NOT_READY, manual live trade should not be taken now. If READY: Log decision before manual exchange action. App does not place orders.</p>
    </section>

    <h2>Machine Trade Ticket</h2>
    <section id="tradeTicket" class="ticket blocked">
      <div class="grid">
        <div><div class="label">ticket_status</div><div id="ticketStatus" class="value danger">loading</div></div>
        <div><div class="label">readiness_status</div><div id="ticketReadiness" class="value danger">loading</div></div>
        <div><div class="label">allowed_now</div><div id="ticketAllowed" class="value danger">false</div></div>
        <div><div class="label">signal_id</div><div id="ticketSignal" class="value mono">loading</div></div>
        <div><div class="label">direction/timeframe</div><div id="ticketDirection" class="value">loading</div></div>
        <div><div class="label">entry</div><div id="ticketEntry" class="value">loading</div></div>
        <div><div class="label">stop</div><div id="ticketStop" class="value">loading</div></div>
        <div><div class="label">take_profit</div><div id="ticketTakeProfit" class="value">loading</div></div>
        <div><div class="label">suggested_position_usd</div><div id="ticketPosition" class="value">loading</div></div>
        <div><div class="label">suggested_leverage</div><div id="ticketLeverage" class="value">loading</div></div>
        <div><div class="label">max_loss_usd</div><div id="ticketMaxLoss" class="value">loading</div></div>
        <div><div class="label">margin_mode</div><div id="ticketMargin" class="value">isolated</div></div>
        <div><div class="label">live_execution_enabled</div><div id="ticketLive" class="value danger">false</div></div>
        <div><div class="label">order_placed</div><div id="ticketOrder" class="value danger">false</div></div>
      </div>
      <p><strong>Blockers:</strong> <span id="ticketBlockers">loading</span></p>
      <p><strong>Machine reason:</strong> <span id="ticketReason">loading</span></p>
      <p class="muted">No order will be placed. This records approval intent only.</p>
      <p class="muted">Paper execution only. No live order will be placed.</p>
      <p id="paperExecutionBlocked" class="muted">Blocked: no paper execution without PROPOSED ticket.</p>
      <p><input id="ticketNotes" class="notes" placeholder="paper ticket approval notes"></p>
      <div class="button-row">
        <button class="approve" id="approveTicketButton" onclick="approvePaperTicket()" disabled>Approve Paper Ticket</button>
        <button class="approve" id="executePaperButton" onclick="executePaperTicket()" disabled>Execute Paper Ticket</button>
        <button class="reject" onclick="recordTicketWatch()">Reject / Watch</button>
      </div>
    </section>

    <h2>Exchange Dry Run</h2>
    <section id="exchangeDryRun" class="exchange-dry-run blocked">
      <div class="grid">
        <div><div class="label">validation_status</div><div id="dryRunStatus" class="value danger">loading</div></div>
        <div><div class="label">exchange</div><div id="dryRunExchange" class="value">loading</div></div>
        <div><div class="label">symbol</div><div id="dryRunSymbol" class="value">loading</div></div>
        <div><div class="label">side</div><div id="dryRunSide" class="value">loading</div></div>
        <div><div class="label">position_side</div><div id="dryRunPositionSide" class="value">loading</div></div>
        <div><div class="label">notional_usd</div><div id="dryRunNotional" class="value">loading</div></div>
        <div><div class="label">quantity_rounded</div><div id="dryRunQuantity" class="value">loading</div></div>
        <div><div class="label">entry_price_rounded</div><div id="dryRunEntry" class="value">loading</div></div>
        <div><div class="label">stop_price_rounded</div><div id="dryRunStop" class="value">loading</div></div>
        <div><div class="label">take_profit_price_rounded</div><div id="dryRunTakeProfit" class="value">loading</div></div>
        <div><div class="label">leverage</div><div id="dryRunLeverage" class="value">loading</div></div>
        <div><div class="label">margin_mode</div><div id="dryRunMargin" class="value">loading</div></div>
        <div><div class="label">live_execution_enabled</div><div id="dryRunLive" class="value danger">false</div></div>
        <div><div class="label">order_placed</div><div id="dryRunOrder" class="value danger">false</div></div>
        <div><div class="label">dry_run</div><div id="dryRunFlag" class="value safe">true</div></div>
      </div>
      <p><strong>Blockers:</strong> <span id="dryRunBlockers">loading</span></p>
      <p class="muted">Exchange dry run only. No order was sent. No API key used. No Binance order placement exists.</p>
    </section>

    <h2>Live Safety Envelope</h2>
    <section id="liveSafety" class="live-safety blocked">
      <div class="grid">
        <div><div class="label">live_safety_status</div><div id="liveSafetyStatus" class="value danger">loading</div></div>
        <div><div class="label">live_execution_enabled</div><div id="liveSafetyEnabled" class="value danger">false</div></div>
        <div><div class="label">order_placed</div><div id="liveSafetyOrder" class="value danger">false</div></div>
        <div><div class="label">kill_switch_active</div><div id="liveSafetyKill" class="value danger">true</div></div>
        <div><div class="label">allow_live_orders</div><div id="liveSafetyAllow" class="value danger">false</div></div>
      </div>
      <p><strong>Blockers:</strong> <span id="liveSafetyBlockers">loading</span></p>
      <p><strong>Failed gates:</strong> <span id="liveSafetyFailed">loading</span></p>
      <p><strong>Passed gates:</strong> <span id="liveSafetyPassed">loading</span></p>
      <p><strong>Next required action:</strong> <span id="liveSafetyNext">loading</span></p>
      <p><strong>Protocol:</strong> <span id="liveSafetyProtocol">44 USDT max, 2x preferred, 3x max, isolated margin, 1 trade/day, stop after -5 USDT or 1 loss.</span></p>
      <p class="muted">Live execution is disabled. Kill switch is active by default. No live order can be placed from this system in the current mode. This panel is a safety pre-check only.</p>
    </section>

    <h2>Live Connector Stub</h2>
    <section id="liveConnectorStub" class="live-connector blocked">
      <div class="grid">
        <div><div class="label">connector_mode</div><div id="connectorMode" class="value danger">stub_no_order</div></div>
        <div><div class="label">live_execution_enabled</div><div id="connectorLive" class="value danger">false</div></div>
        <div><div class="label">order_placed</div><div id="connectorOrder" class="value danger">false</div></div>
        <div><div class="label">safety status</div><div id="connectorSafety" class="value danger">loading</div></div>
        <div><div class="label">kill switch active</div><div id="connectorKill" class="value danger">true</div></div>
      </div>
      <p><strong>Last live attempt:</strong> <span id="lastLiveAttempt">loading</span></p>
      <p class="muted">No real order can be placed. Stub connector only records rejected attempts. No API key is used. No Binance/network call exists.</p>
      <div class="button-row">
        <button class="reject" id="stubSubmitButton" onclick="submitLiveConnectorStub()" disabled>Test Live Connector Stub</button>
        <span class="muted">Records rejected no-order attempt</span>
      </div>
    </section>

    <h2>Binance Read-Only Connector</h2>
    <section id="binanceReadonly" class="binance-readonly blocked">
      <div class="grid">
        <div><div class="label">connector_status</div><div id="binanceStatus" class="value danger">loading</div></div>
        <div><div class="label">connector_mode</div><div id="binanceMode" class="value">loading</div></div>
        <div><div class="label">api_key_present</div><div id="binanceApiKeyPresent" class="value">false</div></div>
        <div><div class="label">api_secret_present</div><div id="binanceApiSecretPresent" class="value">false</div></div>
        <div><div class="label">api_key_preview</div><div id="binanceApiKeyPreview" class="value mono">n/a</div></div>
        <div><div class="label">live_trading_env</div><div id="binanceLiveTradingEnv" class="value danger">loading</div></div>
        <div><div class="label">live_execution_enabled</div><div id="binanceLive" class="value danger">false</div></div>
        <div><div class="label">order_placed</div><div id="binanceOrder" class="value danger">false</div></div>
      </div>
      <p><strong>Blockers:</strong> <span id="binanceBlockers">loading</span></p>
      <p><strong>Forbidden actions:</strong> <span id="binanceForbidden">loading</span></p>
      <p class="muted">Read-only connector. No order placement exists.</p>
      <p class="muted">Secrets are never shown. Live trading env must remain false.</p>
    </section>

    <h2>Paper Executions</h2>
    <div id="paperExecutions">loading</div>

    <section class="controls">
      <div class="controls-grid">
        <label><input id="latestOnly" type="checkbox" checked> Latest only</label>
        <label><input id="eligibleOnly" type="checkbox"> Eligible only</label>
        <label><input id="includeForbidden" type="checkbox" checked> Include forbidden</label>
        <label><input id="allowShort" type="checkbox"> Allow short</label>
        <label>Limit <input id="limit" type="number" min="1" max="100" value="10"></label>
        <label>Operator <input id="operator" type="text" value="josue"></label>
        <button onclick="refreshAll()">Refresh</button>
      </div>
    </section>

    <h2>Candidates</h2>
    <div id="candidates">loading</div>

    <h2>Recent Decisions</h2>
    <div id="decisions">loading</div>

    <h2>Last Action</h2>
    <section id="message" class="feedback">No action yet. order_placed=false.</section>
  </main>
<script>
let currentCandidates = [];
let currentTicket = null;

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

async function refreshAll() {
  await loadHealth();
  await loadReadiness();
  await loadTradeTicket();
  await loadExchangeDryRun();
  await loadLiveSafety();
  await loadLiveAttempts();
  await loadBinanceReadonlyStatus();
  await loadPaperExecutions();
  await loadCandidates();
  await loadDecisions();
}

async function loadHealth() {
  const res = await fetch('/health');
  const data = await res.json();
  document.getElementById('health').textContent = data.ok ? 'ok' : 'not ok';
  document.getElementById('live').textContent = String(data.live_execution_enabled);
}

async function loadReadiness() {
  const res = await fetch('/readiness');
  const data = await res.json();
  const state = data.current_state || {};
  const root = document.getElementById('readiness');
  const isReady = data.readiness_status === 'READY';
  root.className = 'readiness ' + (isReady ? 'ready' : 'not-ready');
  document.getElementById('readyStatus').textContent = data.readiness_status || 'UNKNOWN';
  document.getElementById('readyStatus').className = 'value ' + (isReady ? 'safe' : 'danger');
  document.getElementById('allowedNow').textContent = String(data.allowed_now === true);
  document.getElementById('allowedNow').className = 'value ' + (data.allowed_now === true ? 'safe' : 'danger');
  document.getElementById('freshEligible').textContent = String(state.fresh_eligible_count ?? 0);
  document.getElementById('outcomesToday').textContent = String(state.manual_outcomes_today ?? 0);
  document.getElementById('lossesToday').textContent = String(state.losses_today ?? 0);
  document.getElementById('pnlToday').textContent = String(state.pnl_usd_today ?? 0);
  document.getElementById('readinessLive').textContent = String(data.live_execution_enabled);
  document.getElementById('readinessOrder').textContent = String(data.order_placed);
  document.getElementById('readinessReason').textContent = data.reason_summary || '';
  document.getElementById('readinessBlockers').textContent = (data.blockers || []).length ? data.blockers.join('; ') : 'none';
  document.getElementById('nextAction').textContent = data.next_required_action || '';
  if (!isReady) {
    document.getElementById('readinessReason').textContent = (data.reason_summary || '') + ' Manual live trade should not be taken now.';
  }
}

async function loadTradeTicket() {
  const params = new URLSearchParams({
    latest_only: document.getElementById('latestOnly')?.checked ? 'true' : 'false',
    allow_short: document.getElementById('allowShort')?.checked ? 'true' : 'false'
  });
  const res = await fetch('/trade-ticket?' + params.toString());
  const data = await res.json();
  currentTicket = data;
  const status = data.ticket_status || 'BLOCKED';
  const proposed = status === 'PROPOSED';
  const root = document.getElementById('tradeTicket');
  root.className = 'ticket ' + (status === 'EXPIRED' ? 'expired' : (proposed ? 'proposed' : 'blocked'));
  document.getElementById('ticketStatus').textContent = status;
  document.getElementById('ticketStatus').className = 'value ' + (proposed ? 'safe' : 'danger');
  document.getElementById('ticketReadiness').textContent = data.readiness_status || 'UNKNOWN';
  document.getElementById('ticketReadiness').className = 'value ' + (data.readiness_status === 'READY' ? 'safe' : 'danger');
  document.getElementById('ticketAllowed').textContent = String(data.allowed_now === true);
  document.getElementById('ticketAllowed').className = 'value ' + (data.allowed_now === true ? 'safe' : 'danger');
  document.getElementById('ticketSignal').textContent = data.signal_id || 'n/a';
  document.getElementById('ticketDirection').textContent = `${data.direction || 'n/a'}/${data.timeframe || 'n/a'}`;
  document.getElementById('ticketEntry').textContent = String(data.entry ?? 'n/a');
  document.getElementById('ticketStop').textContent = String(data.stop ?? 'n/a');
  document.getElementById('ticketTakeProfit').textContent = String(data.take_profit ?? 'n/a');
  document.getElementById('ticketPosition').textContent = String(data.suggested_position_usd ?? 'n/a');
  document.getElementById('ticketLeverage').textContent = String(data.suggested_leverage ?? 'n/a');
  document.getElementById('ticketMaxLoss').textContent = String(data.max_loss_usd ?? 'n/a');
  document.getElementById('ticketMargin').textContent = data.margin_mode || 'isolated';
  document.getElementById('ticketLive').textContent = String(data.live_execution_enabled);
  document.getElementById('ticketOrder').textContent = String(data.order_placed);
  document.getElementById('ticketBlockers').textContent = (data.blockers || []).length ? data.blockers.join('; ') : 'none';
  document.getElementById('ticketReason').textContent = data.machine_reason || '';
  document.getElementById('approveTicketButton').disabled = !proposed;
  document.getElementById('executePaperButton').disabled = !proposed;
  document.getElementById('paperExecutionBlocked').style.display = proposed ? 'none' : 'block';
  document.getElementById('stubSubmitButton').disabled = !data.ticket_id;
}

async function loadExchangeDryRun() {
  const params = new URLSearchParams({
    allow_short: document.getElementById('allowShort')?.checked ? 'true' : 'false'
  });
  const res = await fetch('/exchange-dry-run?' + params.toString());
  const data = await res.json();
  const valid = data.validation_status === 'VALID';
  const root = document.getElementById('exchangeDryRun');
  root.className = 'exchange-dry-run ' + (valid ? 'proposed' : 'blocked');
  document.getElementById('dryRunStatus').textContent = data.validation_status || 'BLOCKED';
  document.getElementById('dryRunStatus').className = 'value ' + (valid ? 'safe' : 'danger');
  document.getElementById('dryRunExchange').textContent = data.exchange || 'n/a';
  document.getElementById('dryRunSymbol').textContent = data.symbol || 'n/a';
  document.getElementById('dryRunSide').textContent = data.side || 'n/a';
  document.getElementById('dryRunPositionSide').textContent = data.position_side || 'n/a';
  document.getElementById('dryRunNotional').textContent = String(data.notional_usd ?? 'n/a');
  document.getElementById('dryRunQuantity').textContent = String(data.quantity_rounded ?? 'n/a');
  document.getElementById('dryRunEntry').textContent = String(data.entry_price_rounded ?? 'n/a');
  document.getElementById('dryRunStop').textContent = String(data.stop_price_rounded ?? 'n/a');
  document.getElementById('dryRunTakeProfit').textContent = String(data.take_profit_price_rounded ?? 'n/a');
  document.getElementById('dryRunLeverage').textContent = String(data.leverage ?? 'n/a');
  document.getElementById('dryRunMargin').textContent = data.margin_mode || 'n/a';
  document.getElementById('dryRunLive').textContent = String(data.live_execution_enabled);
  document.getElementById('dryRunOrder').textContent = String(data.order_placed);
  document.getElementById('dryRunFlag').textContent = String(data.dry_run === true);
  document.getElementById('dryRunBlockers').textContent = (data.blockers || []).length ? data.blockers.join('; ') : 'none';
}

async function loadLiveSafety() {
  const params = new URLSearchParams({
    allow_short: document.getElementById('allowShort')?.checked ? 'true' : 'false'
  });
  const res = await fetch('/live-safety?' + params.toString());
  const data = await res.json();
  const allowed = data.live_safety_status === 'WOULD_BE_ALLOWED_IF_LIVE_ENABLED';
  const root = document.getElementById('liveSafety');
  root.className = 'live-safety ' + (allowed ? 'proposed' : 'blocked');
  document.getElementById('liveSafetyStatus').textContent = data.live_safety_status || 'BLOCKED';
  document.getElementById('liveSafetyStatus').className = 'value ' + (allowed ? 'safe' : 'danger');
  document.getElementById('liveSafetyEnabled').textContent = String(data.live_execution_enabled);
  document.getElementById('liveSafetyOrder').textContent = String(data.order_placed);
  document.getElementById('liveSafetyKill').textContent = String(data.kill_switch_active);
  document.getElementById('liveSafetyAllow').textContent = String(data.allow_live_orders);
  document.getElementById('liveSafetyBlockers').textContent = (data.blockers || []).length ? data.blockers.join('; ') : 'none';
  document.getElementById('liveSafetyFailed').textContent = (data.failed_gates || []).length ? data.failed_gates.join(', ') : 'none';
  document.getElementById('liveSafetyPassed').textContent = (data.passed_gates || []).length ? data.passed_gates.join(', ') : 'none';
  document.getElementById('liveSafetyNext').textContent = data.next_required_action || '';
  const protocol = data.protocol || {};
  document.getElementById('liveSafetyProtocol').textContent = `${protocol.max_position_usd ?? 44} USDT max, ${protocol.preferred_leverage ?? 2}x preferred, ${protocol.max_leverage ?? 3}x max, ${protocol.margin_mode || 'isolated'} margin, ${protocol.max_trades_per_day ?? 1} trade/day, ${protocol.hard_daily_stop || 'stop after -5 USDT or 1 loss'}.`;
  document.getElementById('connectorSafety').textContent = data.live_safety_status || 'BLOCKED';
  document.getElementById('connectorKill').textContent = String(data.kill_switch_active);
}

async function submitLiveConnectorStub() {
  if (!currentTicket || !currentTicket.ticket_id) return;
  const operatorInput = document.getElementById('operator');
  const notesInput = document.getElementById('ticketNotes');
  const body = {
    ticket_id: currentTicket.ticket_id,
    operator: operatorInput ? operatorInput.value || 'josue' : 'josue',
    notes: notesInput ? notesInput.value : ''
  };
  const res = await fetch('/live-connector/stub-submit', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body)
  });
  const data = await res.json();
  const message = document.getElementById('message');
  if (!res.ok) {
    message.className = 'feedback error';
    message.innerHTML = `<strong>API error ${res.status}</strong><pre>${esc(JSON.stringify(data, null, 2))}</pre>`;
  } else {
    message.className = 'feedback success';
    message.innerHTML = `<strong>Live connector stub attempt recorded:</strong> live_attempt_id=${esc(data.live_attempt_id)} | connector_mode=${esc(data.connector_mode)} | rejected=${esc(data.rejected)} | order_placed=${esc(data.order_placed)}`;
  }
  await loadLiveAttempts();
}

async function loadLiveAttempts() {
  const res = await fetch('/live-connector/attempts?limit=1');
  const data = await res.json();
  document.getElementById('connectorMode').textContent = data.connector_mode || 'stub_no_order';
  document.getElementById('connectorLive').textContent = String(data.live_execution_enabled);
  document.getElementById('connectorOrder').textContent = String(data.order_placed);
  const attempts = data.live_attempts || [];
  if (!attempts.length) {
    document.getElementById('lastLiveAttempt').textContent = 'none';
    return;
  }
  const latest = attempts[0];
  document.getElementById('lastLiveAttempt').textContent = `${latest.created_at} | ${latest.live_attempt_id} | rejected=${latest.rejected} | order_placed=${latest.order_placed}`;
}

async function loadBinanceReadonlyStatus() {
  const res = await fetch('/binance-readonly/status');
  const data = await res.json();
  const ready = data.connector_status === 'READY_READ_ONLY';
  const root = document.getElementById('binanceReadonly');
  root.className = 'binance-readonly ' + (ready ? 'proposed' : 'blocked');
  document.getElementById('binanceStatus').textContent = data.connector_status || 'MISSING_ENV';
  document.getElementById('binanceStatus').className = 'value ' + (ready ? 'safe' : 'danger');
  document.getElementById('binanceMode').textContent = data.connector_mode || 'n/a';
  document.getElementById('binanceApiKeyPresent').textContent = String(data.api_key_present === true);
  document.getElementById('binanceApiSecretPresent').textContent = String(data.api_secret_present === true);
  document.getElementById('binanceApiKeyPreview').textContent = data.api_key_preview || 'n/a';
  document.getElementById('binanceLiveTradingEnv').textContent = data.live_trading_env || 'n/a';
  document.getElementById('binanceLive').textContent = String(data.live_execution_enabled);
  document.getElementById('binanceOrder').textContent = String(data.order_placed);
  document.getElementById('binanceBlockers').textContent = (data.blockers || []).length ? data.blockers.join('; ') : 'none';
  document.getElementById('binanceForbidden').textContent = (data.forbidden_actions || []).join(', ');
}

async function loadCandidates() {
  const params = new URLSearchParams({
    latest_only: document.getElementById('latestOnly').checked ? 'true' : 'false',
    allow_short: document.getElementById('allowShort').checked ? 'true' : 'false',
    limit: document.getElementById('limit').value || '10'
  });
  const res = await fetch('/candidates?' + params.toString());
  const data = await res.json();
  document.getElementById('archive').textContent = data.archive_log_dir || 'n/a';
  document.getElementById('generated').textContent = data.generated_at || 'n/a';
  document.getElementById('live').textContent = String(data.live_execution_enabled);
  document.getElementById('order').textContent = String(data.order_placed);
  currentCandidates = data.candidates || [];
  const eligibleOnly = document.getElementById('eligibleOnly').checked;
  const includeForbidden = document.getElementById('includeForbidden').checked;
  const visible = currentCandidates.filter(c => {
    if (eligibleOnly && c.decision !== 'ELIGIBLE_TINY_LIVE') return false;
    if (!includeForbidden && c.decision === 'FORBIDDEN') return false;
    return true;
  });
  const root = document.getElementById('candidates');
  if (visible.length === 0) {
    root.innerHTML = '<div class="candidate">No candidates returned.</div>';
    return;
  }
  root.innerHTML = visible.map(c => renderCandidate(c, currentCandidates.indexOf(c))).join('');
}

function decisionClass(decision) {
  if (decision === 'ELIGIBLE_TINY_LIVE') return 'eligible';
  if (decision === 'PAPER_ONLY') return 'paper';
  if (decision === 'FORBIDDEN') return 'forbidden';
  return 'paper';
}

function renderCandidate(c, index) {
  const cls = decisionClass(c.decision);
  const canApprove = c.decision === 'ELIGIBLE_TINY_LIVE';
  const disabledText = c.decision === 'FORBIDDEN'
    ? 'Blocked: candidate is FORBIDDEN'
    : 'Blocked: candidate is PAPER_ONLY';
  return `<section class="candidate candidate-${cls}">
    <div><span class="badge badge-${cls}">${esc(c.decision)}</span></div>
    <div class="grid">
      <div><div class="label">signal_id</div><div class="value mono">${esc(c.signal_id)}</div></div>
      <div><div class="label">decision</div><div class="value">${esc(c.decision)}</div></div>
      <div><div class="label">reason</div><div class="value">${esc(c.reason)}</div></div>
      <div><div class="label">direction/timeframe</div><div class="value">${esc(c.direction)}/${esc(c.timeframe)}</div></div>
      <div><div class="label">entry</div><div class="value">${esc(c.entry)}</div></div>
      <div><div class="label">stop</div><div class="value">${esc(c.stop)}</div></div>
      <div><div class="label">take_profit</div><div class="value">${esc(c.take_profit)}</div></div>
      <div><div class="label">age_minutes</div><div class="value">${esc(c.age_minutes)}</div></div>
      <div><div class="label">freshness_status</div><div class="value">${esc(c.freshness_status)}</div></div>
      <div><div class="label">capped_max_position_size_usd</div><div class="value">${esc(c.capped_max_position_size_usd)}</div></div>
      <div><div class="label">suggested_leverage</div><div class="value">${esc(c.suggested_leverage)}</div></div>
      <div><div class="label">score/tier</div><div class="value">${esc(c.score)} / ${esc(c.tier)}</div></div>
      <div><div class="label">live_execution_enabled</div><div class="value danger">${esc(c.live_execution_enabled)}</div></div>
      <div><div class="label">order_placed</div><div class="value danger">${esc(c.order_placed)}</div></div>
    </div>
    <p><input id="notes-${index}" class="notes" placeholder="notes"></p>
    <div class="button-row">
      <button onclick="recordDecision(${index}, 'watch')">Watch</button>
      <button class="reject" onclick="recordDecision(${index}, 'reject')">Reject</button>
      <button onclick="recordDecision(${index}, 'paper_only')">Paper Only</button>
      <button class="approve" onclick="recordDecision(${index}, 'approve_manual_live')" ${canApprove ? '' : 'disabled'} title="${canApprove ? 'Record approval intent only' : disabledText}">Log Manual-Live Intent</button>
    </div>
    ${canApprove ? '' : `<div class="muted">${disabledText}. Watch / Reject / Paper Only remain available.</div>`}
  </section>`;
}

async function approvePaperTicket() {
  if (!currentTicket || !currentTicket.ticket_id) return;
  const operatorInput = document.getElementById('operator');
  const notesInput = document.getElementById('ticketNotes');
  const body = {
    ticket_id: currentTicket.ticket_id,
    operator: operatorInput ? operatorInput.value || 'josue' : 'josue',
    notes: notesInput ? notesInput.value : '',
    ticket_snapshot: currentTicket
  };
  const res = await fetch('/trade-ticket/approve-paper', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body)
  });
  const data = await res.json();
  const message = document.getElementById('message');
  if (!res.ok) {
    message.className = 'feedback error';
    message.innerHTML = `<strong>API error ${res.status}</strong><pre>${esc(JSON.stringify(data, null, 2))}</pre>`;
  } else {
    message.className = 'feedback success';
    message.innerHTML = `<strong>Paper ticket approval intent recorded:</strong> ticket_id=${esc(data.ticket.ticket_id)} | order_placed=${esc(data.order_placed)} | paper_order_placed=${esc(data.paper_order_placed)}`;
  }
}

async function executePaperTicket() {
  if (!currentTicket || !currentTicket.ticket_id) return;
  const operatorInput = document.getElementById('operator');
  const notesInput = document.getElementById('ticketNotes');
  const body = {
    ticket_id: currentTicket.ticket_id,
    operator: operatorInput ? operatorInput.value || 'josue' : 'josue',
    notes: notesInput ? notesInput.value : ''
  };
  const res = await fetch('/trade-ticket/execute-paper', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body)
  });
  const data = await res.json();
  const message = document.getElementById('message');
  if (!res.ok) {
    message.className = 'feedback error';
    message.innerHTML = `<strong>API error ${res.status}</strong><pre>${esc(JSON.stringify(data, null, 2))}</pre>`;
  } else {
    message.className = 'feedback success';
    message.innerHTML = `<strong>Paper execution recorded:</strong> paper_execution_id=${esc(data.paper_execution_id)} | paper_order_placed=${esc(data.paper_order_placed)} | order_placed=${esc(data.order_placed)} | live_execution_enabled=${esc(data.live_execution_enabled)}`;
  }
  await loadPaperExecutions();
}

function recordTicketWatch() {
  const message = document.getElementById('message');
  message.className = 'feedback';
  message.textContent = 'Ticket marked for watch/reject in operator console only. No order will be placed.';
}

async function loadPaperExecutions() {
  const res = await fetch('/paper-executions?limit=10');
  const data = await res.json();
  const root = document.getElementById('paperExecutions');
  if (!data.paper_executions || data.paper_executions.length === 0) {
    root.innerHTML = '<div class="paper-execution">No paper execution records.</div>';
    return;
  }
  root.innerHTML = data.paper_executions.map(record => `<div class="paper-execution">
    <div class="grid">
      <div><div class="label">created_at</div><div class="value">${esc(record.created_at)}</div></div>
      <div><div class="label">paper_execution_id</div><div class="value mono">${esc(record.paper_execution_id)}</div></div>
      <div><div class="label">signal_id</div><div class="value mono">${esc(record.signal_id)}</div></div>
      <div><div class="label">direction/timeframe</div><div class="value">${esc(record.direction)}/${esc(record.timeframe)}</div></div>
      <div><div class="label">position_usd</div><div class="value">${esc(record.position_usd)}</div></div>
      <div><div class="label">leverage</div><div class="value">${esc(record.leverage)}</div></div>
      <div><div class="label">status</div><div class="value">${esc(record.status)}</div></div>
      <div><div class="label">paper_order_placed</div><div class="value safe">${esc(record.paper_order_placed)}</div></div>
      <div><div class="label">order_placed</div><div class="value danger">${esc(record.order_placed)}</div></div>
    </div>
  </div>`).join('');
}

async function recordDecision(index, decision) {
  const candidate = currentCandidates[index];
  if (!candidate) return;
  const signalId = candidate.signal_id;
  const notesInput = document.getElementById(`notes-${index}`);
  const operatorInput = document.getElementById('operator');
  const body = {
    signal_id: signalId,
    decision,
    operator: operatorInput ? operatorInput.value || 'josue' : 'josue',
    notes: notesInput ? notesInput.value : '',
    intended_position_usd: decision === 'approve_manual_live' ? 44 : 0,
    intended_leverage: decision === 'approve_manual_live' ? 2 : 0
  };
  const res = await fetch('/decisions', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body)
  });
  const data = await res.json();
  const message = document.getElementById('message');
  document.getElementById('order').textContent = String(data.order_placed === true);
  if (!res.ok) {
    message.className = 'feedback error';
    message.innerHTML = `<strong>API error ${res.status}</strong><pre>${esc(JSON.stringify(data, null, 2))}</pre>`;
  } else {
    message.className = 'feedback success';
    message.innerHTML = `<strong>Decision recorded:</strong> ${esc(data.decision)} | signal_id=${esc(data.signal_id)} | order_placed=${esc(data.order_placed)}`;
  }
  await loadDecisions();
}

async function loadDecisions() {
  const res = await fetch('/decisions?limit=10');
  const data = await res.json();
  const root = document.getElementById('decisions');
  if (!data.decisions || data.decisions.length === 0) {
    root.innerHTML = '<div class="decision">No decisions logged.</div>';
    return;
  }
  root.innerHTML = data.decisions.map(d => `<div class="decision">
    <div class="grid">
      <div><div class="label">created_at</div><div class="value">${esc(d.created_at)}</div></div>
      <div><div class="label">signal_id</div><div class="value mono">${esc(d.signal_id)}</div></div>
      <div><div class="label">decision</div><div class="value">${esc(d.decision)}</div></div>
      <div><div class="label">operator</div><div class="value">${esc(d.operator)}</div></div>
      <div><div class="label">order_placed</div><div class="value danger">${esc(d.order_placed)}</div></div>
      <div><div class="label">live_execution_enabled</div><div class="value danger">${esc(d.live_execution_enabled)}</div></div>
    </div>
    <div>${esc(d.notes)}</div>
  </div>`).join('');
}

refreshAll();
['latestOnly', 'eligibleOnly', 'includeForbidden', 'allowShort', 'limit'].forEach(id => {
  document.addEventListener('change', event => {
    if (event.target && event.target.id === id) {
      loadTradeTicket();
      loadExchangeDryRun();
      loadLiveSafety();
      loadCandidates();
    }
  });
});
setInterval(refreshAll, 30000);
</script>
</body>
</html>"""


def main() -> int:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8015)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
