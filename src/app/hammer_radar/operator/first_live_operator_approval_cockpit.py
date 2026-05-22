"""R108 first-live operator approval cockpit.

This module composes existing first-live readiness gates into a UI-safe cockpit
state and records operator approval intent only. It never enables live
execution, places orders, creates signed payloads, or calls Binance order
endpoints.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.final_live_preflight import READY, build_final_live_preflight
from src.app.hammer_radar.operator.first_live_activation_gate import (
    FIRST_LIVE_ACTIVATION_READY,
    build_first_live_activation_gate,
)
from src.app.hammer_radar.operator.one_tiny_live_order_protocol import (
    CONFIRMATION_PHRASE_TEMPLATE,
    PROTOCOL_PREREQS_READY,
    build_one_tiny_live_order_protocol_check,
)
from src.app.hammer_radar.operator.tiny_live_armed_dry_run import (
    READY_FOR_DRY_RUN,
    build_tiny_live_armed_dry_run,
)
from src.app.hammer_radar.operator.tiny_live_risk_contract import DEFAULT_CANDIDATE_ID

EVENT_TYPE = "OPERATOR_APPROVAL_COCKPIT_INTENT"
INTENTS_FILENAME = "operator_approval_cockpit_intents.ndjson"
SOURCE_SURFACE = "operator.first_live_operator_approval_cockpit.build_operator_approval_cockpit_state"
WINDOW_SECONDS = 15 * 60
SACRED_BUTTON_COPY = "This does not place an order."

VALID_INTENTS = {"APPROVE", "REJECT", "WAIT"}
VALID_COUNSEL_DECISIONS = {"APPROVE", "REJECT", "WAIT", "ESCALATE"}


def build_operator_approval_cockpit_state(
    *,
    candidate_id: str = DEFAULT_CANDIDATE_ID,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    checked_at = _utc(now)

    final_preflight = build_final_live_preflight(candidate_id=candidate_id, log_dir=resolved_log_dir, env=env)
    dry_run = build_tiny_live_armed_dry_run(candidate_id=candidate_id, log_dir=resolved_log_dir, env=env, record=False)
    protocol = build_one_tiny_live_order_protocol_check(candidate_id=candidate_id, log_dir=resolved_log_dir, env=env, record=False)
    activation_gate = build_first_live_activation_gate(candidate_id=candidate_id, log_dir=resolved_log_dir, env=env, record=False)

    resolved_candidate_id = (
        activation_gate.get("candidate_id")
        or dry_run.get("candidate_id")
        or protocol.get("candidate_id")
        or final_preflight.get("candidate_id")
        or candidate_id
    )
    risk_contract_hash = activation_gate.get("risk_contract_hash") or dry_run.get("risk_contract_hash") or final_preflight.get("risk_contract_hash")
    packet_hash = activation_gate.get("packet_hash") or dry_run.get("packet_hash") or final_preflight.get("final_review_packet_hash")
    window = _approval_window(activation_gate=activation_gate, risk_contract_hash=risk_contract_hash, packet_hash=packet_hash, now=checked_at)
    latest_intent = _latest_cockpit_intent(candidate_id=str(resolved_candidate_id or ""), log_dir=resolved_log_dir)

    blockers = _dedupe(
        [
            *[str(item) for item in activation_gate.get("blockers") or []],
            *[f"final preflight: {item}" for item in final_preflight.get("blockers") or []],
        ]
    )
    warnings = _dedupe(
        [
            *[str(item) for item in activation_gate.get("warnings") or []],
            "Cockpit approval records operator intent only and cannot place a real order.",
            "R106 first-live activation gate remains backend authority.",
        ]
    )
    status = _cockpit_status(
        activation_status=str(activation_gate.get("status") or ""),
        window_status=window["approval_window_status"],
        latest_intent=latest_intent,
    )
    can_approve = (
        activation_gate.get("status") == FIRST_LIVE_ACTIVATION_READY
        and window["approval_window_status"] == "OPEN"
        and bool(resolved_candidate_id)
        and bool(risk_contract_hash)
        and bool(packet_hash)
    )
    sequence_steps = _sequence_steps(
        final_preflight=final_preflight,
        dry_run=dry_run,
        protocol=protocol,
        activation_gate=activation_gate,
        window=window,
        latest_intent=latest_intent,
    )
    sacred_button_state = _sacred_button_state(
        can_record_intent=can_approve,
        activation_gate=activation_gate,
        window=window,
        latest_intent=latest_intent,
        candidate_id=resolved_candidate_id,
        risk_contract_hash=risk_contract_hash,
        packet_hash=packet_hash,
    )
    blocker_summary = _blocker_summary(
        blockers=blockers,
        final_preflight=final_preflight,
        dry_run=dry_run,
        protocol=protocol,
        activation_gate=activation_gate,
        sequence_steps=sequence_steps,
    )
    operator_path_to_press = _operator_path_to_press(
        final_preflight=final_preflight,
        dry_run=dry_run,
        protocol=protocol,
        activation_gate=activation_gate,
        window=window,
        candidate_id=resolved_candidate_id,
        risk_contract_hash=risk_contract_hash,
        packet_hash=packet_hash,
    )

    state = {
        "status": status,
        "checked_at_utc": checked_at.isoformat(),
        "first_live_activation_gate_status": activation_gate.get("status"),
        "final_preflight_status": final_preflight.get("status"),
        "tiny_live_armed_dry_run_status": dry_run.get("status"),
        "protocol_status": protocol.get("status"),
        "candidate_id": resolved_candidate_id,
        "risk_contract_hash": risk_contract_hash,
        "packet_hash": packet_hash,
        "counsel_decision": (latest_intent or {}).get("counsel_decision") or "WAIT",
        "counsel_tags": list((latest_intent or {}).get("counsel_tags") or ["R108", "INTENT_ONLY", "R106_GATE_AUTHORITY"]),
        **window,
        "sacred_button_state": sacred_button_state,
        "blocker_summary": blocker_summary,
        "operator_path_to_press": operator_path_to_press,
        "sequence_steps": sequence_steps,
        "simultaneous_signals": [
            _signal_card(
                candidate_id=str(resolved_candidate_id or ""),
                risk_contract_hash=risk_contract_hash,
                packet_hash=packet_hash,
                activation_gate=activation_gate,
                final_preflight=final_preflight,
                window=window,
                can_record_intent=can_approve,
                latest_intent=latest_intent,
            )
        ],
        "blockers": blockers,
        "warnings": warnings,
        "live_ready": False,
        "execution_enabled_by_ui": False,
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "real_order_possible": False,
        "secrets_shown": False,
        "source_surfaces_used": _source_surfaces(
            final_preflight=final_preflight,
            dry_run=dry_run,
            protocol=protocol,
            activation_gate=activation_gate,
        ),
        "backend_authority": {
            "r106_first_live_activation_gate": activation_gate.get("status"),
            "ui_approval_is_execution_authority": False,
            "telegram_approval_is_execution_authority": False,
            "confirmation_phrase_required": True,
            "confirmation_phrase_template": CONFIRMATION_PHRASE_TEMPLATE,
            "sacred_button_can_place_order": False,
        },
        "latest_intent": latest_intent,
        "intent_ledger_path": str(operator_approval_cockpit_intents_path(resolved_log_dir)),
    }
    return _sanitize(state)


def record_operator_approval_cockpit_intent(
    *,
    candidate_id: str,
    intent: str,
    counsel_decision: str,
    counsel_tags: list[str],
    risk_contract_hash: str,
    packet_hash: str,
    operator_note: str | None = None,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    checked_at = _utc(now)
    state = build_operator_approval_cockpit_state(candidate_id=candidate_id, log_dir=resolved_log_dir, env=env, now=checked_at)
    rejection_reason = _intent_rejection_reason(
        state=state,
        candidate_id=candidate_id,
        risk_contract_hash=risk_contract_hash,
        packet_hash=packet_hash,
        intent=intent,
        counsel_decision=counsel_decision,
        counsel_tags=counsel_tags,
    )
    accepted = rejection_reason is None
    record = {
        "event_type": EVENT_TYPE,
        "intent_id": uuid4().hex,
        "recorded_at_utc": checked_at.isoformat(),
        "candidate_id": candidate_id,
        "intent": intent,
        "counsel_decision": counsel_decision,
        "counsel_tags": _normalize_tags(counsel_tags),
        "risk_contract_hash": risk_contract_hash,
        "packet_hash": packet_hash,
        "operator_note": operator_note or "",
        "approval_window_status": state.get("approval_window_status"),
        "approval_window_expires_at_utc": state.get("approval_window_expires_at_utc"),
        "accepted_as_intent": accepted,
        "rejection_reason": rejection_reason,
        "message": "Intent recorded only. No order was placed." if accepted else str(rejection_reason or "intent rejected"),
        "first_live_activation_gate_status": state.get("first_live_activation_gate_status"),
        "sacred_button_state": state.get("sacred_button_state") or _fallback_sacred_button_state(state),
        "live_ready": False,
        "execution_enabled_by_ui": False,
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "real_order_possible": False,
        "secrets_shown": False,
    }
    append_operator_approval_cockpit_intent(record, log_dir=resolved_log_dir)
    current_state = build_operator_approval_cockpit_state(candidate_id=candidate_id, log_dir=resolved_log_dir, env=env, now=checked_at)
    message = "Intent recorded only. No order was placed." if accepted else str(rejection_reason or "intent rejected")
    return _sanitize(
        {
            "status": "INTENT_RECORDED" if accepted else "INTENT_REJECTED",
            "accepted_as_intent": accepted,
            "rejection_reason": rejection_reason,
            "message": message,
            "first_live_activation_gate_status": state.get("first_live_activation_gate_status"),
            "current_r106_gate_status": state.get("first_live_activation_gate_status"),
            "sacred_button_state": current_state.get("sacred_button_state") or state.get("sacred_button_state") or _fallback_sacred_button_state(state),
            "record": record,
            "current_state": current_state,
            "live_ready": False,
            "execution_enabled_by_ui": False,
            "order_placed": False,
            "real_order_placed": False,
            "execution_attempted": False,
            "real_order_possible": False,
            "secrets_shown": False,
        }
    )


def append_operator_approval_cockpit_intent(record: dict[str, Any], *, log_dir: str | Path) -> None:
    path = operator_approval_cockpit_intents_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_sanitize(record), sort_keys=True) + "\n")


def load_operator_approval_cockpit_intents(
    *,
    limit: int = 50,
    intent_id: str | None = None,
    candidate_id: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = operator_approval_cockpit_intents_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = _sanitize(json.loads(line))
            if intent_id is not None and record.get("intent_id") != intent_id:
                continue
            if candidate_id is not None and record.get("candidate_id") != candidate_id:
                continue
            records.append(record)
    records = list(reversed(records))
    if limit > 0:
        return records[:limit]
    return records


def operator_approval_cockpit_intents_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / INTENTS_FILENAME


def operator_approval_cockpit_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>R109 First-Live Cockpit Sacred Button Hardening</title>
  <style>
    :root { color-scheme: dark; font-family: Arial, sans-serif; background: #070707; color: #f8fafc; }
    body { margin: 0; background: #070707; }
    header { padding: 22px; border-bottom: 1px solid #4c0519; background: linear-gradient(135deg, #1f0508, #111827); }
    main { max-width: 1180px; margin: 0 auto; padding: 20px; }
    .guard { padding: 14px 20px; background: #450a0a; color: #fee2e2; font-weight: 900; letter-spacing: .02em; }
    .banner { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
    .banner span { padding: 6px 10px; border: 1px solid #fb7185; border-radius: 6px; background: #7f1d1d; font-weight: 900; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; }
    .panel, .step, .signal { border: 1px solid #334155; border-radius: 8px; background: #111827; padding: 14px; margin-bottom: 14px; }
    .ready { border-color: #22c55e; }
    .blocked { border-color: #ef4444; }
    .expired { border-color: #f59e0b; }
    .intent { border-color: #38bdf8; }
    .label { color: #94a3b8; font-size: 12px; text-transform: uppercase; }
    .value { font-weight: 800; overflow-wrap: anywhere; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
    .tag { display: inline-block; margin: 3px 4px 3px 0; padding: 4px 8px; border-radius: 999px; background: #1e293b; border: 1px solid #475569; font-size: 12px; font-weight: 800; }
    .hourglass { font-size: 26px; font-weight: 900; }
    .countdown { font-size: 48px; font-weight: 900; color: #fee2e2; }
    .bar { height: 14px; border: 1px solid #7f1d1d; border-radius: 999px; overflow: hidden; background: #1f2937; }
    .bar-fill { height: 100%; width: 0%; background: linear-gradient(90deg, #ef4444, #f59e0b); }
    .sacred { text-align: center; border-color: #ef4444; background: radial-gradient(circle at 50% 22%, #7f1d1d 0, #1f0508 42%, #111827 100%); }
    .eye-wrap { display: grid; place-items: center; margin: 10px auto; }
    .eye { width: min(460px, 90vw); aspect-ratio: 2.4 / 1; border: 5px solid #ef4444; border-radius: 50%; display: grid; place-items: center; background: #2b0507; box-shadow: 0 0 34px rgba(239,68,68,.55); }
    .eye-inner { width: 120px; height: 120px; border-radius: 50%; background: radial-gradient(circle, #fef2f2 0 10%, #ef4444 11% 34%, #450a0a 35% 100%); border: 4px solid #fecaca; box-shadow: 0 0 28px rgba(254,202,202,.7); }
    .sacred-button { width: min(620px, 100%); min-height: 96px; margin: 10px auto; display: block; background: #991b1b; border-color: #fecaca; box-shadow: 0 0 24px rgba(239,68,68,.45); }
    .sacred-button:disabled { background: #2f1111; border-color: #7f1d1d; color: #fecaca; box-shadow: none; }
    .path { border-left: 4px solid #475569; padding-left: 10px; margin: 8px 0; }
    .path.ok { border-color: #22c55e; }
    .path.block { border-color: #ef4444; }
    .buttons { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 10px; margin-top: 12px; }
    button { min-height: 70px; border-radius: 8px; border: 2px solid #64748b; background: #1e293b; color: #f8fafc; font-size: 20px; font-weight: 900; cursor: pointer; }
    button.approve { background: #14532d; border-color: #22c55e; }
    button.reject { background: #7f1d1d; border-color: #ef4444; }
    button.wait { background: #78350f; border-color: #f59e0b; }
    button:disabled { background: #1f2937; color: #64748b; border-color: #374151; cursor: not-allowed; }
    input, textarea, select { width: 100%; box-sizing: border-box; padding: 9px; border-radius: 6px; border: 1px solid #475569; background: #020617; color: #f8fafc; }
    pre { white-space: pre-wrap; background: #020617; border: 1px solid #334155; border-radius: 8px; padding: 12px; }
  </style>
</head>
<body>
  <header>
    <h1>FIRST LIVE COCKPIT</h1>
    <div class="banner">
      <span>INTENT ONLY</span>
      <span>NO ORDER CAN BE PLACED</span>
      <span>R106 GATE AUTHORITY</span>
    </div>
  </header>
  <div class="guard">This UI cannot place real orders, cannot enable execution, and cannot override backend gates. The sacred button records intent only.</div>
  <main>
    <section id="summary" class="panel blocked">
      <div class="grid">
        <div><div class="label">Cockpit status</div><div id="status" class="value">loading</div></div>
        <div><div class="label">R106 gate</div><div id="gate" class="value">loading</div></div>
        <div><div class="label">Window</div><div id="window" class="value">loading</div></div>
        <div><div class="label">Hourglass</div><div id="hourglass" class="hourglass">...</div></div>
        <div><div class="label">live_ready</div><div class="value">false</div></div>
        <div><div class="label">execution_enabled_by_ui</div><div class="value">false</div></div>
        <div><div class="label">order_placed</div><div class="value">false</div></div>
        <div><div class="label">real_order_possible</div><div class="value">false</div></div>
      </div>
    </section>

    <section id="sacredPanel" class="panel sacred blocked">
      <div class="label">Sacred final-button visual</div>
      <div class="eye-wrap"><div class="eye" aria-hidden="true"><div class="eye-inner"></div></div></div>
      <button id="sacredButton" class="sacred-button" onclick="recordIntent('APPROVE')">SACRED BUTTON LOCKED</button>
      <div id="sacredReason" class="value">loading</div>
      <p>Confirmation phrase requirement: <span id="confirmationPhrase" class="mono"></span></p>
      <p><strong>This does not place an order.</strong></p>
    </section>

    <section class="panel">
      <h2>Approval Countdown</h2>
      <div class="grid">
        <div><div class="label">Hourglass</div><div id="countdownIcon" class="hourglass">hourglass</div></div>
        <div><div class="label">Seconds remaining</div><div id="countdown" class="countdown">0s</div></div>
        <div><div class="label">Window status</div><div id="windowLarge" class="value">loading</div></div>
      </div>
      <div class="bar"><div id="countdownBar" class="bar-fill"></div></div>
    </section>

    <h2>Required Gate Order</h2>
    <section id="sequence"></section>

    <h2>Simultaneous Signals</h2>
    <section id="signals"></section>

    <section class="panel">
      <h2>How The Sacred Button Eventually Becomes Pressable</h2>
      <div id="operatorPath"></div>
      <p>Even then, this cockpit only records intent.</p>
    </section>

    <section class="panel">
      <h2>Record Counsel / Operator Intent</h2>
      <div class="grid">
        <div><div class="label">candidate_id</div><input id="candidateId"></div>
        <div><div class="label">risk_contract_hash</div><input id="riskHash"></div>
        <div><div class="label">packet_hash</div><input id="packetHash"></div>
        <div><div class="label">counsel_decision</div><select id="counsel"><option>WAIT</option><option>APPROVE</option><option>REJECT</option><option>ESCALATE</option></select></div>
      </div>
      <p><div class="label">counsel_tags comma separated</div><input id="tags" value="R108,INTENT_ONLY,R106_GATE_AUTHORITY"></p>
      <p><div class="label">operator_note optional</div><textarea id="note" rows="3"></textarea></p>
      <div class="buttons">
        <button id="approve" class="approve" onclick="recordIntent('APPROVE')">APPROVE INTENT ONLY</button>
        <button id="reject" class="reject" onclick="recordIntent('REJECT')">REJECT INTENT ONLY</button>
        <button id="wait" class="wait" onclick="recordIntent('WAIT')">WAIT INTENT ONLY</button>
      </div>
      <p id="intentMessage"></p>
    </section>

    <section class="panel">
      <h2>Backend Evidence</h2>
      <pre id="raw">loading</pre>
    </section>
  </main>
  <script>
    let state = null;
    function esc(value) {
      return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    }
    function tags(items) {
      return (items || []).map(item => `<span class="tag">${esc(item)}</span>`).join('');
    }
    function panelClass(status) {
      if (status === 'INTENT_RECORDED') return 'intent';
      if (status === 'REVIEWABLE') return 'ready';
      if (status === 'LOCKED') return 'blocked';
      if (status === 'EXPIRED') return 'expired';
      if (status === 'READY_FOR_REVIEW' || status === 'READY' || status === 'FIRST_LIVE_ACTIVATION_READY') return 'ready';
      return 'blocked';
    }
    function shortHash(value) {
      const text = String(value || '');
      return text.length > 14 ? `${text.slice(0, 8)}...${text.slice(-6)}` : text;
    }
    async function loadState() {
      const response = await fetch('/operator/approval-cockpit/state');
      state = await response.json();
      const sacred = state.sacred_button_state || {};
      document.getElementById('status').textContent = state.status;
      document.getElementById('gate').textContent = state.first_live_activation_gate_status;
      document.getElementById('window').textContent = `${state.approval_window_status} ${state.approval_window_seconds_remaining ?? 'n/a'}s`;
      document.getElementById('hourglass').textContent = state.approval_window_status === 'OPEN' ? `hourglass ${state.approval_window_seconds_remaining}s` : state.approval_window_status;
      document.getElementById('summary').className = `panel ${panelClass(state.status)}`;
      document.getElementById('sacredPanel').className = `panel sacred ${panelClass(sacred.visual_state)}`;
      document.getElementById('sacredButton').textContent = sacred.label || 'SACRED BUTTON LOCKED';
      document.getElementById('sacredButton').disabled = !sacred.enabled;
      document.getElementById('sacredReason').textContent = sacred.reason || '';
      document.getElementById('confirmationPhrase').textContent = sacred.confirmation_phrase_template || 'future confirmation phrase required';
      const seconds = Number(state.approval_window_seconds_remaining || 0);
      const pct = Math.max(0, Math.min(100, (seconds / 900) * 100));
      document.getElementById('countdown').textContent = `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
      document.getElementById('windowLarge').textContent = state.approval_window_status || 'MISSING';
      document.getElementById('countdownIcon').textContent = state.approval_window_status === 'OPEN' ? 'hourglass active' : 'hourglass locked';
      document.getElementById('countdownBar').style.width = `${pct}%`;
      document.getElementById('candidateId').value = state.candidate_id || '';
      document.getElementById('riskHash').value = state.risk_contract_hash || '';
      document.getElementById('packetHash').value = state.packet_hash || '';
      document.getElementById('counsel').value = state.counsel_decision || 'WAIT';
      document.getElementById('tags').value = (state.counsel_tags || []).join(',');
      const disabled = !sacred.enabled;
      for (const id of ['approve', 'reject', 'wait']) document.getElementById(id).disabled = disabled;
      document.getElementById('sequence').innerHTML = state.sequence_steps.map(step => `
        <div class="step ${panelClass(step.status)}">
          <div class="grid">
            <div><div class="label">step</div><div class="value">${esc(step.label)}</div></div>
            <div><div class="label">status</div><div class="value">${esc(step.status)}</div></div>
            <div><div class="label">required</div><div class="value">${esc(step.required)}</div></div>
            <div><div class="label">blockers</div><div class="value">${esc(step.blocker_count)}</div></div>
            <div><div class="label">blocks sacred button</div><div class="value">${esc(step.blocks_sacred_button)}</div></div>
            <div><div class="label">can_approve</div><div class="value">${esc(step.can_approve)}</div></div>
            <div><div class="label">expires_at_utc</div><div class="value mono">${esc(step.expires_at_utc || 'n/a')}</div></div>
          </div>
        </div>`).join('');
      document.getElementById('signals').innerHTML = state.simultaneous_signals.map(signal => `
        <div class="signal ${panelClass(signal.approval_window_status)}">
          <div class="grid">
            <div><div class="label">candidate</div><div class="value mono">${esc(signal.candidate_id)}</div></div>
            <div><div class="label">symbol</div><div class="value">${esc(signal.symbol)}</div></div>
            <div><div class="label">timeframe</div><div class="value">${esc(signal.timeframe)}</div></div>
            <div><div class="label">direction</div><div class="value">${esc(signal.direction)}</div></div>
            <div><div class="label">score</div><div class="value">${esc(signal.score ?? 'n/a')}</div></div>
            <div><div class="label">counsel</div><div class="value">${esc(signal.counsel_decision)}</div></div>
            <div><div class="label">window</div><div class="value">${esc(signal.approval_window_status)} ${esc(signal.seconds_remaining ?? 'n/a')}s</div></div>
            <div><div class="label">R106 authority</div><div class="value">true</div></div>
            <div><div class="label">intent only</div><div class="value">true</div></div>
            <div><div class="label">can_record_intent</div><div class="value">${esc(signal.can_record_intent)}</div></div>
            <div><div class="label">risk hash</div><div class="value mono" title="${esc(signal.risk_contract_hash || '')}">${esc(signal.risk_contract_hash_short || shortHash(signal.risk_contract_hash))}</div></div>
            <div><div class="label">packet hash</div><div class="value mono" title="${esc(signal.packet_hash || '')}">${esc(signal.packet_hash_short || shortHash(signal.packet_hash))}</div></div>
          </div>
          <p>${tags(signal.tags)}</p>
          <p><strong>Blockers:</strong> ${esc((signal.blockers || []).join('; ') || 'none')}</p>
          <p><strong>Warnings:</strong> ${esc((signal.warnings || []).join('; ') || 'none')}</p>
        </div>`).join('');
      document.getElementById('operatorPath').innerHTML = (state.operator_path_to_press || []).map(step => `
        <div class="path ${step.satisfied ? 'ok' : 'block'}">
          <div class="value">${esc(step.label)}</div>
          <div>${esc(step.current_status)} must become ${esc(step.required_status)}</div>
          <div class="label">${esc(step.next_action_hint)}</div>
        </div>`).join('');
      document.getElementById('raw').textContent = JSON.stringify(state, null, 2);
    }
    async function recordIntent(intent) {
      const payload = {
        candidate_id: document.getElementById('candidateId').value,
        intent,
        counsel_decision: document.getElementById('counsel').value,
        counsel_tags: document.getElementById('tags').value.split(',').map(x => x.trim()).filter(Boolean),
        risk_contract_hash: document.getElementById('riskHash').value,
        packet_hash: document.getElementById('packetHash').value,
        operator_note: document.getElementById('note').value
      };
      const response = await fetch('/operator/approval-cockpit/intent', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
      });
      const data = await response.json();
      document.getElementById('intentMessage').textContent = response.ok ? `${data.message} ${data.record.intent_id}` : `INTENT_REJECTED ${JSON.stringify(data.detail || data)}`;
      await loadState();
    }
    loadState();
    setInterval(loadState, 10000);
  </script>
</body>
</html>"""


def _sequence_steps(
    *,
    final_preflight: Mapping[str, Any],
    dry_run: Mapping[str, Any],
    protocol: Mapping[str, Any],
    activation_gate: Mapping[str, Any],
    window: Mapping[str, Any],
    latest_intent: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    return [
        _step("final preflight", final_preflight.get("status"), final_preflight.get("blockers"), final_preflight.get("status") == READY),
        _step("armed dry run", dry_run.get("status"), dry_run.get("blockers"), dry_run.get("status") == READY_FOR_DRY_RUN),
        _step(
            "one tiny live order protocol",
            protocol.get("status"),
            protocol.get("blockers"),
            protocol.get("status") == PROTOCOL_PREREQS_READY,
        ),
        _step(
            "first live activation gate",
            activation_gate.get("status"),
            activation_gate.get("blockers"),
            activation_gate.get("status") == FIRST_LIVE_ACTIVATION_READY,
        ),
        {
            "label": "operator approval intent",
            "status": "INTENT_RECORDED" if latest_intent and latest_intent.get("accepted_as_intent") else "READY_FOR_REVIEW",
            "required": True,
            "blocker_count": 0 if latest_intent and latest_intent.get("accepted_as_intent") else 1,
            "can_approve": activation_gate.get("status") == FIRST_LIVE_ACTIVATION_READY and window.get("approval_window_status") == "OPEN",
            "blocks_sacred_button": not (
                activation_gate.get("status") == FIRST_LIVE_ACTIVATION_READY and window.get("approval_window_status") == "OPEN"
            ),
            "expires_at_utc": window.get("approval_window_expires_at_utc"),
        },
        {
            "label": "confirmation phrase requirement",
            "status": "BLOCKED",
            "required": True,
            "blocker_count": 1,
            "can_approve": False,
            "blocks_sacred_button": True,
            "expires_at_utc": None,
        },
    ]


def _step(label: str, status: Any, blockers: Any, can_approve: bool) -> dict[str, Any]:
    return {
        "label": label,
        "status": str(status or "BLOCKED"),
        "required": True,
        "blocker_count": len(list(blockers or [])),
        "can_approve": bool(can_approve),
        "blocks_sacred_button": not bool(can_approve),
        "expires_at_utc": None,
    }


def _sacred_button_state(
    *,
    can_record_intent: bool,
    activation_gate: Mapping[str, Any],
    window: Mapping[str, Any],
    latest_intent: Mapping[str, Any] | None,
    candidate_id: Any,
    risk_contract_hash: Any,
    packet_hash: Any,
) -> dict[str, Any]:
    if latest_intent and latest_intent.get("accepted_as_intent") is True:
        label = "RECORD INTENT ONLY"
        visual_state = "INTENT_RECORDED"
        reason = "Latest accepted operator intent is already recorded; the cockpit still cannot place an order."
    elif window.get("approval_window_status") == "EXPIRED":
        label = "EXPIRED"
        visual_state = "EXPIRED"
        reason = "Approval window expired; refresh the R102-R106 evidence chain before recording intent."
    elif activation_gate.get("status") != FIRST_LIVE_ACTIVATION_READY:
        label = "BLOCKED BY R106"
        visual_state = "LOCKED"
        reason = "R106 first-live activation gate is not FIRST_LIVE_ACTIVATION_READY."
    elif not candidate_id or not risk_contract_hash or not packet_hash:
        label = "SACRED BUTTON LOCKED"
        visual_state = "LOCKED"
        reason = "Candidate id, risk contract hash, and packet hash must all be present."
    elif can_record_intent:
        label = "RECORD INTENT ONLY"
        visual_state = "REVIEWABLE"
        reason = "Intent prerequisites are satisfied; pressing records intent only and cannot place an order."
    else:
        label = "SACRED BUTTON LOCKED"
        visual_state = "LOCKED"
        reason = "Intent prerequisites are incomplete."
    return {
        "label": label,
        "enabled": bool(can_record_intent),
        "reason": reason,
        "visual_state": visual_state,
        "can_place_order": False,
        "records_intent_only": True,
        "confirmation_phrase_required": True,
        "confirmation_phrase_template": CONFIRMATION_PHRASE_TEMPLATE,
        "safety_copy": SACRED_BUTTON_COPY,
    }


def _fallback_sacred_button_state(state: Mapping[str, Any]) -> dict[str, Any]:
    window_status = state.get("approval_window_status")
    gate_status = state.get("first_live_activation_gate_status")
    if window_status == "EXPIRED":
        label = "EXPIRED"
        visual_state = "EXPIRED"
        reason = "Approval window expired."
    elif gate_status != FIRST_LIVE_ACTIVATION_READY:
        label = "BLOCKED BY R106"
        visual_state = "LOCKED"
        reason = "R106 first-live activation gate is not ready."
    elif window_status == "OPEN":
        label = "RECORD INTENT ONLY"
        visual_state = "REVIEWABLE"
        reason = "Intent prerequisites are satisfied."
    else:
        label = "SACRED BUTTON LOCKED"
        visual_state = "LOCKED"
        reason = "Approval window is not open."
    return {
        "label": label,
        "enabled": bool(gate_status == FIRST_LIVE_ACTIVATION_READY and window_status == "OPEN"),
        "reason": reason,
        "visual_state": visual_state,
        "can_place_order": False,
        "records_intent_only": True,
        "confirmation_phrase_required": True,
        "confirmation_phrase_template": CONFIRMATION_PHRASE_TEMPLATE,
        "safety_copy": SACRED_BUTTON_COPY,
    }


def _blocker_summary(
    *,
    blockers: list[str],
    final_preflight: Mapping[str, Any],
    dry_run: Mapping[str, Any],
    protocol: Mapping[str, Any],
    activation_gate: Mapping[str, Any],
    sequence_steps: list[Mapping[str, Any]],
) -> dict[str, Any]:
    sequence_blockers = [
        f"{step.get('label')} is {step.get('status')}"
        for step in sequence_steps
        if step.get("blocks_sacred_button") or step.get("blocker_count")
    ]
    primary = _dedupe([*sequence_blockers, *blockers])[:5]
    return {
        "primary_blockers": primary,
        "detailed_blocker_count": len(blockers),
        "final_preflight_blocker_count": len(list(final_preflight.get("blockers") or [])),
        "dry_run_blocker_count": len(list(dry_run.get("blockers") or [])),
        "protocol_blocker_count": len(list(protocol.get("blockers") or [])),
        "activation_gate_blocker_count": len(list(activation_gate.get("blockers") or [])),
    }


def _operator_path_to_press(
    *,
    final_preflight: Mapping[str, Any],
    dry_run: Mapping[str, Any],
    protocol: Mapping[str, Any],
    activation_gate: Mapping[str, Any],
    window: Mapping[str, Any],
    candidate_id: Any,
    risk_contract_hash: Any,
    packet_hash: Any,
) -> list[dict[str, Any]]:
    return [
        _path_step("R102 final preflight", final_preflight.get("status"), READY, "Resolve final preflight blockers."),
        _path_step("R104 tiny-live armed dry run", dry_run.get("status"), READY_FOR_DRY_RUN, "Run the armed dry-run evidence chain."),
        _path_step(
            "R105 one tiny live order protocol",
            protocol.get("status"),
            PROTOCOL_PREREQS_READY,
            "Satisfy protocol prerequisites without executing.",
        ),
        _path_step(
            "R106 first-live activation gate",
            activation_gate.get("status"),
            FIRST_LIVE_ACTIVATION_READY,
            "R106 must be ready; it remains backend authority.",
        ),
        _path_step("Approval window", window.get("approval_window_status"), "OPEN", "Refresh evidence before the countdown expires."),
        {
            "label": "Candidate/hash tuple",
            "current_status": "MATCHABLE" if candidate_id and risk_contract_hash and packet_hash else "MISSING",
            "required_status": "MATCHABLE",
            "satisfied": bool(candidate_id and risk_contract_hash and packet_hash),
            "next_action_hint": "Candidate id, risk contract hash, and packet hash must match the R106 evidence.",
        },
        {
            "label": "Confirmation phrase",
            "current_status": "FUTURE_PHASE_REQUIRED",
            "required_status": "SUPPLIED_IN_FUTURE_EXECUTION_PHASE",
            "satisfied": False,
            "next_action_hint": "Supply the exact confirmation phrase only in a future explicitly authorized execution phase.",
        },
        {
            "label": "Cockpit authority",
            "current_status": "INTENT_ONLY",
            "required_status": "INTENT_ONLY",
            "satisfied": True,
            "next_action_hint": "Even when pressable, this cockpit only records intent and cannot place an order.",
        },
    ]


def _path_step(label: str, current_status: Any, required_status: str, next_action_hint: str) -> dict[str, Any]:
    current = str(current_status or "MISSING")
    return {
        "label": label,
        "current_status": current,
        "required_status": required_status,
        "satisfied": current == required_status,
        "next_action_hint": next_action_hint,
    }


def _signal_card(
    *,
    candidate_id: str,
    risk_contract_hash: Any,
    packet_hash: Any,
    activation_gate: Mapping[str, Any],
    final_preflight: Mapping[str, Any],
    window: Mapping[str, Any],
    can_record_intent: bool,
    latest_intent: Mapping[str, Any] | None,
) -> dict[str, Any]:
    parsed = _parse_candidate_id(candidate_id)
    return {
        "candidate_id": candidate_id,
        "symbol": parsed.get("symbol"),
        "timeframe": parsed.get("timeframe"),
        "direction": parsed.get("direction"),
        "score": None,
        "risk_contract_hash": risk_contract_hash,
        "packet_hash": packet_hash,
        "counsel_decision": (latest_intent or {}).get("counsel_decision") or "WAIT",
        "tags": _dedupe(
            [
                *(str(item) for item in (latest_intent or {}).get("counsel_tags") or []),
                str(parsed.get("symbol") or "UNKNOWN_SYMBOL"),
                str(parsed.get("timeframe") or "UNKNOWN_TIMEFRAME"),
                str(parsed.get("direction") or "UNKNOWN_DIRECTION"),
                f"COUNSEL_{(latest_intent or {}).get('counsel_decision') or 'WAIT'}",
                f"WINDOW_{window.get('approval_window_status')}",
                "R106_GATE_AUTHORITY",
                "INTENT_ONLY",
            ]
        ),
        "approval_window_status": window.get("approval_window_status"),
        "seconds_remaining": window.get("approval_window_seconds_remaining"),
        "can_record_intent": bool(can_record_intent),
        "risk_contract_hash_short": _short_hash(risk_contract_hash),
        "packet_hash_short": _short_hash(packet_hash),
        "blockers": list(activation_gate.get("blockers") or []),
        "warnings": list(final_preflight.get("warnings") or []),
    }


def _approval_window(*, activation_gate: Mapping[str, Any], risk_contract_hash: Any, packet_hash: Any, now: datetime) -> dict[str, Any]:
    if not risk_contract_hash or not packet_hash:
        return {
            "approval_window_opened_at_utc": None,
            "approval_window_expires_at_utc": None,
            "approval_window_seconds_remaining": 0,
            "approval_window_status": "MISSING",
        }
    opened_at = _parse_dt(activation_gate.get("checked_at_utc") or activation_gate.get("recorded_at_utc")) or now
    expires_at = opened_at + timedelta(seconds=WINDOW_SECONDS)
    seconds_remaining = max(0, int((expires_at - now).total_seconds()))
    return {
        "approval_window_opened_at_utc": opened_at.isoformat(),
        "approval_window_expires_at_utc": expires_at.isoformat(),
        "approval_window_seconds_remaining": seconds_remaining,
        "approval_window_status": "OPEN" if seconds_remaining > 0 else "EXPIRED",
    }


def _intent_rejection_reason(
    *,
    state: Mapping[str, Any],
    candidate_id: str,
    risk_contract_hash: str,
    packet_hash: str,
    intent: str,
    counsel_decision: str,
    counsel_tags: list[str],
) -> str | None:
    if intent not in VALID_INTENTS:
        return "invalid intent"
    if counsel_decision not in VALID_COUNSEL_DECISIONS:
        return "invalid counsel_decision"
    if len(_normalize_tags(counsel_tags)) != len(counsel_tags):
        return "invalid counsel_tags"
    if not state.get("candidate_id") or not state.get("risk_contract_hash") or not state.get("packet_hash"):
        return "missing candidate or hash data"
    if state.get("approval_window_status") != "OPEN":
        return f"approval window is {state.get('approval_window_status') or 'MISSING'}"
    if candidate_id != state.get("candidate_id"):
        return "candidate_id mismatch"
    if risk_contract_hash != state.get("risk_contract_hash"):
        return "risk_contract_hash mismatch"
    if packet_hash != state.get("packet_hash"):
        return "packet_hash mismatch"
    if state.get("first_live_activation_gate_status") != FIRST_LIVE_ACTIVATION_READY:
        return "R106 first-live activation gate is not ready"
    return None


def _source_surfaces(
    *,
    final_preflight: Mapping[str, Any],
    dry_run: Mapping[str, Any],
    protocol: Mapping[str, Any],
    activation_gate: Mapping[str, Any],
) -> list[str]:
    sources = [
        SOURCE_SURFACE,
        "operator.final_live_preflight.build_final_live_preflight",
        "operator.tiny_live_armed_dry_run.build_tiny_live_armed_dry_run",
        "operator.one_tiny_live_order_protocol.build_one_tiny_live_order_protocol_check",
        "operator.first_live_activation_gate.build_first_live_activation_gate",
        "R106 first-live activation gate",
    ]
    for payload in (final_preflight, dry_run, protocol, activation_gate):
        sources.extend(str(item) for item in payload.get("source_surfaces_used") or [])
    return _dedupe(sources)


def _cockpit_status(*, activation_status: str, window_status: str, latest_intent: Mapping[str, Any] | None) -> str:
    if latest_intent and latest_intent.get("accepted_as_intent") is True:
        return "INTENT_RECORDED"
    if window_status == "EXPIRED":
        return "EXPIRED"
    if activation_status == FIRST_LIVE_ACTIVATION_READY and window_status == "OPEN":
        return "READY_FOR_REVIEW"
    return "BLOCKED"


def _latest_cockpit_intent(*, candidate_id: str, log_dir: Path) -> dict[str, Any] | None:
    records = load_operator_approval_cockpit_intents(limit=1, candidate_id=candidate_id, log_dir=log_dir)
    return records[0] if records else None


def _parse_candidate_id(candidate_id: str) -> dict[str, str | None]:
    parts = str(candidate_id or "").split("|")
    return {
        "symbol": parts[1] if len(parts) > 1 else None,
        "timeframe": parts[2] if len(parts) > 2 else None,
        "direction": parts[3] if len(parts) > 3 else None,
    }


def _normalize_tags(tags: list[str]) -> list[str]:
    normalized: list[str] = []
    for tag in tags:
        item = str(tag or "").strip().upper()
        if not item or len(item) > 40 or not all(char.isalnum() or char in {"_", "-"} for char in item):
            continue
        normalized.append(item)
    return normalized[:12]


def _short_hash(value: Any) -> str | None:
    if not value:
        return None
    text = str(value)
    if len(text) <= 14:
        return text
    return f"{text[:8]}...{text[-6:]}"


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return _utc(parsed)


def _utc(value: datetime | None = None) -> datetime:
    current = value or datetime.now(UTC)
    if current.tzinfo is None:
        return current.replace(tzinfo=UTC)
    return current.astimezone(UTC)


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(str(item) for item in items if str(item)))


def _sanitize(payload: Any) -> Any:
    if isinstance(payload, dict):
        sanitized = {str(key): _sanitize(value) for key, value in payload.items()}
        for key in list(sanitized):
            lower = key.lower()
            if any(token in lower for token in ("api_key", "api_secret", "secret", "token", "signature")) and lower not in {
                "secrets_shown",
            }:
                if lower.endswith("_present"):
                    sanitized[key] = bool(sanitized[key])
                else:
                    sanitized[key] = "[redacted]"
        return sanitized
    if isinstance(payload, list):
        return [_sanitize(item) for item in payload]
    return payload
