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


def _operator_ui_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Hammer Radar Approval Console</title>
  <style>
    :root { color-scheme: light; font-family: Arial, sans-serif; background: #f7f7f5; color: #202124; }
    body { margin: 0; }
    header { padding: 18px 24px; background: #1f2933; color: white; }
    main { max-width: 1180px; margin: 0 auto; padding: 20px; }
    .status, .candidate, .decision { background: white; border: 1px solid #d9ddd6; border-radius: 8px; padding: 14px; margin-bottom: 14px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px; }
    .label { color: #5d675f; font-size: 12px; text-transform: uppercase; }
    .value { font-weight: 700; overflow-wrap: anywhere; }
    .danger { color: #9f1d1d; font-weight: 700; }
    .safe { color: #12613a; font-weight: 700; }
    button { margin: 6px 6px 0 0; padding: 8px 10px; border: 1px solid #aeb7ad; border-radius: 6px; background: #f2f5ef; cursor: pointer; }
    button:hover { background: #e6ece2; }
    input { min-width: 260px; padding: 8px; border: 1px solid #b8c0b6; border-radius: 6px; }
    pre { white-space: pre-wrap; background: #111827; color: #f9fafb; padding: 12px; border-radius: 6px; }
    h2 { margin-top: 28px; }
  </style>
</head>
<body>
  <header>
    <h1>Hammer Radar Approval Console</h1>
    <div>Record Decision only. No order placement. live_execution_enabled=false.</div>
  </header>
  <main>
    <section class="status">
      <div class="grid">
        <div><div class="label">Health</div><div id="health" class="value">loading</div></div>
        <div><div class="label">live_execution_enabled</div><div id="live" class="value danger">false</div></div>
        <div><div class="label">order_placed</div><div id="order" class="value danger">false</div></div>
        <div><div class="label">Archive</div><div id="archive" class="value">loading</div></div>
        <div><div class="label">Generated</div><div id="generated" class="value">loading</div></div>
      </div>
      <button onclick="refreshAll()">Refresh</button>
    </section>

    <h2>Candidates</h2>
    <div id="candidates">loading</div>

    <h2>Recent Decisions</h2>
    <div id="decisions">loading</div>

    <h2>Last Action</h2>
    <pre id="message">No action yet.</pre>
  </main>
<script>
const operatorName = "josue";

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

async function refreshAll() {
  await loadHealth();
  await loadCandidates();
  await loadDecisions();
}

async function loadHealth() {
  const res = await fetch('/health');
  const data = await res.json();
  document.getElementById('health').textContent = data.ok ? 'ok' : 'not ok';
  document.getElementById('live').textContent = String(data.live_execution_enabled);
}

async function loadCandidates() {
  const res = await fetch('/candidates?latest_only=true');
  const data = await res.json();
  document.getElementById('archive').textContent = data.archive_log_dir || 'n/a';
  document.getElementById('generated').textContent = data.generated_at || 'n/a';
  document.getElementById('live').textContent = String(data.live_execution_enabled);
  document.getElementById('order').textContent = String(data.order_placed);
  const root = document.getElementById('candidates');
  if (!data.candidates || data.candidates.length === 0) {
    root.innerHTML = '<div class="candidate">No candidates returned.</div>';
    return;
  }
  root.innerHTML = data.candidates.map(renderCandidate).join('');
}

function renderCandidate(c) {
  const id = esc(c.signal_id);
  return `<section class="candidate">
    <div class="grid">
      <div><div class="label">signal_id</div><div class="value">${id}</div></div>
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
    <p><input id="notes-${id}" placeholder="notes"></p>
    <button onclick="recordDecision('${id}', 'watch')">Watch</button>
    <button onclick="recordDecision('${id}', 'reject')">Reject</button>
    <button onclick="recordDecision('${id}', 'paper_only')">Paper Only</button>
    <button onclick="recordDecision('${id}', 'approve_manual_live')">Approve Manual Live</button>
  </section>`;
}

async function recordDecision(signalId, decision) {
  const notesInput = document.getElementById(`notes-${signalId}`);
  const body = {
    signal_id: signalId,
    decision,
    operator: operatorName,
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
  document.getElementById('message').textContent = JSON.stringify(data, null, 2);
  document.getElementById('order').textContent = String(data.order_placed === true);
  if (!res.ok) {
    document.getElementById('message').textContent = `API error ${res.status}: ` + JSON.stringify(data, null, 2);
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
      <div><div class="label">signal_id</div><div class="value">${esc(d.signal_id)}</div></div>
      <div><div class="label">decision</div><div class="value">${esc(d.decision)}</div></div>
      <div><div class="label">operator</div><div class="value">${esc(d.operator)}</div></div>
      <div><div class="label">order_placed</div><div class="value danger">${esc(d.order_placed)}</div></div>
      <div><div class="label">live_execution_enabled</div><div class="value danger">${esc(d.live_execution_enabled)}</div></div>
    </div>
    <div>${esc(d.notes)}</div>
  </div>`).join('');
}

refreshAll();
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
