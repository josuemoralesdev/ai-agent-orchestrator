"""R133 read-only lane control cockpit.

This module composes existing autonomous lane status surfaces into a compact
operator UI state. It is intentionally read-only: no order payloads, Binance
calls, signed requests, env mutation, lane config writes, or live flag changes.
"""

from __future__ import annotations

import html
import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.autonomous_paper_lane_executor_integration import (
    build_autonomous_paper_lane_executor_integration_status,
    run_autonomous_paper_lane_executor_once,
)
from src.app.hammer_radar.operator.first_tiny_live_autonomous_lane_authorization import (
    build_first_tiny_live_autonomous_lane_authorization,
)
from src.app.hammer_radar.operator.first_tiny_live_lane_execution_gate import (
    TINY_LIVE_EXECUTION_READY,
    build_first_tiny_live_lane_execution_gate,
)
from src.app.hammer_radar.operator.fresh_signal_router import build_fresh_signal_router_status
from src.app.hammer_radar.operator.lane_autonomy_scheduler import run_lane_autonomy_scheduler_once
from src.app.hammer_radar.operator.lane_control import build_lane_control_status, normalize_lane_key
from src.app.hammer_radar.operator.live_adapter_boundary_final_review import (
    LIVE_ADAPTER_BOUNDARY_REVIEW_READY,
    build_live_adapter_boundary_final_review,
)
from src.app.hammer_radar.operator.live_lane_kill_switch_rehearsal import (
    build_live_lane_kill_switch_rehearsal,
)

DEFAULT_LANE_KEY = "BTCUSDT|13m|long|ladder_close_50_618"

COCKPIT_SAFETY = {
    "order_placed": False,
    "real_order_placed": False,
    "execution_attempted": False,
    "order_payload_created": False,
    "network_allowed": False,
    "secrets_shown": False,
    "paper_live_separation_intact": True,
    "env_mutated": False,
    "config_written": False,
    "global_live_flags_changed": False,
    "binance_order_endpoint_called": False,
    "signed_request_created": False,
}

SOURCE_SURFACES_USED = [
    "operator.lane_control.build_lane_control_status",
    "operator.fresh_signal_router.build_fresh_signal_router_status",
    "operator.lane_autonomy_scheduler.run_lane_autonomy_scheduler_once preview",
    "operator.autonomous_paper_lane_executor_integration.build_autonomous_paper_lane_executor_integration_status",
    "operator.autonomous_paper_lane_executor_integration.run_autonomous_paper_lane_executor_once preview",
    "operator.first_tiny_live_lane_execution_gate.build_first_tiny_live_lane_execution_gate record=False",
    "operator.first_tiny_live_autonomous_lane_authorization.build_first_tiny_live_autonomous_lane_authorization preview",
    "operator.live_lane_kill_switch_rehearsal.build_live_lane_kill_switch_rehearsal",
    "operator.live_adapter_boundary_final_review.build_live_adapter_boundary_final_review",
    "configs/hammer_radar/lane_controls.json",
]


def build_lane_control_cockpit_state(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    sources: dict[str, dict[str, Any]] = {}
    failures: list[dict[str, str]] = []

    lane_control = _safe_source("lane_control_status", failures, lambda: build_lane_control_status(log_dir=resolved_log_dir))
    router = _safe_source("fresh_signal_router_status", failures, lambda: build_fresh_signal_router_status(log_dir=resolved_log_dir, now=generated_at))
    scheduler = _safe_source(
        "lane_autonomy_scheduler_status",
        failures,
        lambda: run_lane_autonomy_scheduler_once(log_dir=resolved_log_dir, lane_key=lane_key),
    )
    paper_status = _safe_source(
        "paper_lane_executor_integration_status",
        failures,
        lambda: build_autonomous_paper_lane_executor_integration_status(log_dir=resolved_log_dir),
    )
    paper_preview = _safe_source(
        "paper_lane_executor_integration_preview",
        failures,
        lambda: run_autonomous_paper_lane_executor_once(log_dir=resolved_log_dir, lane_key=lane_key),
    )
    tiny_gate = _safe_source(
        "first_tiny_live_lane_execution_gate",
        failures,
        lambda: build_first_tiny_live_lane_execution_gate(log_dir=resolved_log_dir, lane_key=lane_key, record=False),
    )
    authorization = _safe_source(
        "tiny_live_authorization_status",
        failures,
        lambda: build_first_tiny_live_autonomous_lane_authorization(log_dir=resolved_log_dir, lane_key=lane_key),
    )
    kill_switch = _safe_source(
        "live_lane_kill_switch_rehearsal",
        failures,
        lambda: build_live_lane_kill_switch_rehearsal(log_dir=resolved_log_dir, lane_key=lane_key),
    )
    adapter_boundary = _safe_source(
        "live_adapter_boundary_final_review",
        failures,
        lambda: build_live_adapter_boundary_final_review(log_dir=resolved_log_dir, lane_key=lane_key),
    )
    sources.update(
        {
            "lane_control": lane_control,
            "router": router,
            "scheduler": scheduler,
            "paper_status": paper_status,
            "paper_preview": paper_preview,
            "tiny_gate": tiny_gate,
            "authorization": authorization,
            "kill_switch": kill_switch,
            "adapter_boundary": adapter_boundary,
        }
    )

    lanes = [
        compact_lane_card_state(
            lane,
            router_status=router,
            scheduler_status=scheduler,
            paper_status=paper_status,
            paper_preview=paper_preview,
            tiny_gate=tiny_gate,
            authorization_status=authorization,
            kill_switch_status=kill_switch,
            adapter_boundary_status=adapter_boundary,
        )
        for lane in lane_control.get("lanes", [])
        if isinstance(lane, Mapping)
    ]
    selected_lane = _select_lane_card(lanes, lane_key)
    next_action = compact_next_action_state(
        selected_lane=selected_lane,
        tiny_gate=tiny_gate,
        authorization_status=authorization,
        kill_switch_status=kill_switch,
        adapter_boundary_status=adapter_boundary,
        failures=failures,
        lane_key=lane_key,
    )
    global_safety = compact_global_safety_state(
        lane_control_status=lane_control,
        tiny_gate=tiny_gate,
        authorization_status=authorization,
        kill_switch_status=kill_switch,
        adapter_boundary_status=adapter_boundary,
        failures=failures,
    )
    command_pack = build_cockpit_command_pack(log_dir=resolved_log_dir, lane_key=lane_key)
    status = "LANE_COCKPIT_DEGRADED" if failures else "LANE_COCKPIT_READY"

    return _sanitize(
        {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "read_only": True,
            "no_order_buttons": True,
            "global_safety": global_safety,
            "lanes": lanes,
            "selected_lane": selected_lane,
            "router_summary": _router_summary(router),
            "scheduler_summary": _scheduler_summary(scheduler),
            "paper_executor_summary": _paper_summary(paper_status, paper_preview),
            "tiny_live_gate_summary": _tiny_gate_summary(tiny_gate),
            "authorization_summary": _authorization_summary(authorization),
            "kill_switch_summary": _kill_switch_summary(kill_switch),
            "adapter_boundary_summary": _adapter_boundary_summary(adapter_boundary),
            "next_action": next_action,
            "command_pack": command_pack,
            "safety": dict(COCKPIT_SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
            "source_failures": failures,
            "source_statuses": {name: source.get("status") for name, source in sources.items()},
        }
    )


def compact_lane_card_state(
    lane: Mapping[str, Any],
    *,
    router_status: Mapping[str, Any] | None = None,
    scheduler_status: Mapping[str, Any] | None = None,
    paper_status: Mapping[str, Any] | None = None,
    paper_preview: Mapping[str, Any] | None = None,
    tiny_gate: Mapping[str, Any] | None = None,
    authorization_status: Mapping[str, Any] | None = None,
    kill_switch_status: Mapping[str, Any] | None = None,
    adapter_boundary_status: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    lane_key = str(lane.get("lane_key") or normalize_lane_key(lane.get("symbol"), lane.get("timeframe"), lane.get("direction"), lane.get("entry_mode")))
    route = _latest_route_for_lane(router_status or {}, lane_key)
    scheduler_decisions = [row for row in (scheduler_status or {}).get("decisions", []) if isinstance(row, Mapping)]
    scheduler_decision = next((row for row in scheduler_decisions if str(row.get("lane_key") or "") == lane_key), None)
    selected_gate = (tiny_gate or {}) if _source_lane_matches(tiny_gate or {}, lane_key) else {}
    selected_authorization = (authorization_status or {}) if str((authorization_status or {}).get("lane_key") or "") == lane_key else {}
    selected_kill = (kill_switch_status or {}) if str((kill_switch_status or {}).get("lane_key") or "") == lane_key else {}
    selected_boundary = (adapter_boundary_status or {}) if str((adapter_boundary_status or {}).get("lane_key") or "") == lane_key else {}
    blockers = _dedupe(
        [
            *[str(item) for item in lane.get("blockers") or []],
            *[str(item) for item in (route or {}).get("blockers") or []],
            *[str(item) for item in selected_gate.get("blockers") or []],
            *[str(item) for item in selected_authorization.get("blockers") or []],
            *[str(item) for item in selected_boundary.get("main_blockers") or []],
        ]
    )
    mode = str(lane.get("mode") or "disabled").strip().lower()
    lane_status = str(lane.get("status") or "UNKNOWN")
    return {
        "lane_key": lane_key,
        "symbol": lane.get("symbol"),
        "timeframe": lane.get("timeframe"),
        "direction": lane.get("direction"),
        "entry_mode": lane.get("entry_mode"),
        "current_mode": mode,
        "lane_status": lane_status,
        "freshness_window_seconds": lane.get("freshness_seconds"),
        "live_eligibility_summary": lane.get("live_eligibility") or {},
        "latest_route_status": (route or {}).get("route_status") or "NO_RECENT_ROUTE",
        "latest_route_action": (route or {}).get("route_action") or "IGNORE",
        "candidate_age_seconds": (route or {}).get("candidate_age_seconds"),
        "autonomy_decision_summary": {
            "status": (scheduler_status or {}).get("status"),
            "autonomy_decision": (scheduler_decision or {}).get("autonomy_decision"),
            "scheduler_recorded": False,
        },
        "paper_proof_summary": {
            "status": (paper_status or {}).get("status"),
            "preview_status": (paper_preview or {}).get("status"),
            "recent_integrations_count": len((paper_status or {}).get("recent_integrations") or []),
            "paper_execution_preview_count": len((paper_preview or {}).get("paper_execution_previews") or []),
            "matched": _paper_proof_matched(tiny_gate or {}, authorization_status or {}),
        },
        "tiny_live_gate_status": selected_gate.get("status") or (tiny_gate or {}).get("status") or "UNKNOWN",
        "tiny_live_gate_summary": _tiny_gate_summary(tiny_gate or {}),
        "authorization_status": selected_authorization.get("status") or (authorization_status or {}).get("status") or "UNKNOWN",
        "kill_switch_status": selected_kill.get("status") or (kill_switch_status or {}).get("status") or "UNKNOWN",
        "adapter_boundary_status": selected_boundary.get("status") or (adapter_boundary_status or {}).get("status") or "UNKNOWN",
        "top_blockers": blockers[:6],
        "next_action": _lane_next_action(mode=mode, lane_status=lane_status, blockers=blockers, tiny_gate=tiny_gate or {}, adapter_boundary=adapter_boundary_status or {}),
        "read_only": True,
        "no_order_buttons": True,
        "safety": dict(COCKPIT_SAFETY),
    }


def compact_global_safety_state(
    *,
    lane_control_status: Mapping[str, Any] | None = None,
    tiny_gate: Mapping[str, Any] | None = None,
    authorization_status: Mapping[str, Any] | None = None,
    kill_switch_status: Mapping[str, Any] | None = None,
    adapter_boundary_status: Mapping[str, Any] | None = None,
    failures: list[Mapping[str, str]] | None = None,
) -> dict[str, Any]:
    blockers = _dedupe(
        [
            *[str(item.get("source")) + ": " + str(item.get("error_type")) for item in failures or []],
            *[str(item) for item in (lane_control_status or {}).get("top_blockers") or []],
            *[str(item) for item in (tiny_gate or {}).get("blockers") or []],
            *[str(item) for item in (authorization_status or {}).get("blockers") or []],
            *[str(item) for item in (kill_switch_status or {}).get("current_blockers") or []],
            *[str(item) for item in (adapter_boundary_status or {}).get("main_blockers") or []],
        ]
    )
    if failures:
        status = "SYSTEM REVIEW"
    elif blockers:
        status = "SYSTEM BLOCKED"
    else:
        status = "SYSTEM SAFE"
    return {
        "status": status,
        "order_placed": False,
        "network_allowed": False,
        "secrets_shown": False,
        "global_kill_switch_status": _kill_switch_label(kill_switch_status or {}),
        "paper_live_separation_intact": True,
        "active_lanes_count": (lane_control_status or {}).get("active_lanes_count", 0),
        "configured_lanes_count": (lane_control_status or {}).get("configured_lanes_count", 0),
        "tiny_live_gate_status": (tiny_gate or {}).get("status"),
        "adapter_boundary_status": (adapter_boundary_status or {}).get("status"),
        "top_blockers": blockers[:8],
        "read_only": True,
        "safety": dict(COCKPIT_SAFETY),
    }


def compact_next_action_state(
    *,
    selected_lane: Mapping[str, Any] | None = None,
    tiny_gate: Mapping[str, Any] | None = None,
    authorization_status: Mapping[str, Any] | None = None,
    kill_switch_status: Mapping[str, Any] | None = None,
    adapter_boundary_status: Mapping[str, Any] | None = None,
    failures: list[Mapping[str, str]] | None = None,
    lane_key: str = DEFAULT_LANE_KEY,
) -> dict[str, Any]:
    commands = build_cockpit_command_pack(lane_key=lane_key)
    if failures:
        return {
            "primary": "Review degraded cockpit sources",
            "why": "At least one read-only source failed, so the safest next action is source inspection.",
            "safe_command": commands["lane-control-status"],
            "phase_target": "R133 repair before R134",
            "blockers": [f"{item.get('source')}: {item.get('error_type')}" for item in failures],
        }
    if (adapter_boundary_status or {}).get("status") != LIVE_ADAPTER_BOUNDARY_REVIEW_READY:
        return {
            "primary": "Clear R132 boundary blockers",
            "why": "R134 must not start until the live adapter boundary is visible and blocked/ready state is explicit.",
            "safe_command": commands["live-adapter-boundary-final-review"],
            "phase_target": "R134 only after R132/R133 visibility is clean",
            "blockers": list((adapter_boundary_status or {}).get("main_blockers") or [])[:6],
        }
    if (kill_switch_status or {}).get("status") != "KILL_SWITCH_REHEARSAL_READY":
        return {
            "primary": "Recheck kill-switch rehearsal",
            "why": "Tiny-live review needs a visible rollback and kill-switch rehearsal state.",
            "safe_command": commands["live-lane-kill-switch-rehearsal"],
            "phase_target": "R134 after rehearsal visibility",
            "blockers": list((kill_switch_status or {}).get("current_blockers") or [])[:6],
        }
    if (tiny_gate or {}).get("status") != TINY_LIVE_EXECUTION_READY:
        return {
            "primary": "Inspect tiny-live gate blockers",
            "why": "The final tiny-live gate is still blocked or unknown.",
            "safe_command": commands["first-tiny-live-lane-execution-gate"],
            "phase_target": "R134 after gate visibility",
            "blockers": list((tiny_gate or {}).get("blockers") or [])[:6],
        }
    return {
        "primary": "Prepare R134 dry authorization packet",
        "why": "Cockpit visibility is present; the next phase may draft a non-executing dry authorization packet.",
        "safe_command": commands["live-adapter-boundary-final-review"],
        "phase_target": "R134",
        "blockers": list((selected_lane or {}).get("top_blockers") or [])[:6],
    }


def build_cockpit_command_pack(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_LANE_KEY,
) -> dict[str, str]:
    log_arg = str(log_dir or "logs/hammer_radar_forward")
    prefix = f"PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir {log_arg}"
    return {
        "lane-control-status": f"{prefix} lane-control-status",
        "fresh-signal-router-status": f"{prefix} fresh-signal-router-status",
        "lane-autonomy-scheduler": f"{prefix} lane-autonomy-scheduler --lane-key {json.dumps(lane_key)}",
        "autonomous-paper-lane-executor-integration-preview": f"{prefix} autonomous-paper-lane-executor-integration --lane-key {json.dumps(lane_key)}",
        "first-tiny-live-lane-execution-gate": f"{prefix} first-tiny-live-lane-execution-gate --lane-key {json.dumps(lane_key)}",
        "first-tiny-live-autonomous-lane-authorization-preview": f"{prefix} first-tiny-live-autonomous-lane-authorization --lane-key {json.dumps(lane_key)}",
        "live-lane-kill-switch-rehearsal": f"{prefix} live-lane-kill-switch-rehearsal --lane-key {json.dumps(lane_key)}",
        "live-adapter-boundary-final-review": f"{prefix} live-adapter-boundary-final-review --lane-key {json.dumps(lane_key)}",
    }


def render_lane_control_cockpit_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Hammer Control Tower</title>
  <style>
    :root { color-scheme: dark; font-family: Inter, Arial, sans-serif; background: #07090b; color: #f5f7fb; }
    body { margin: 0; background: radial-gradient(circle at 80% -10%, rgba(120, 53, 15, .28), transparent 28%), #07090b; }
    header { padding: 22px 24px 16px; border-bottom: 1px solid #27272a; background: #0b0d10; }
    h1 { margin: 0; font-size: 34px; letter-spacing: 0; }
    h2 { margin: 0 0 12px; font-size: 16px; color: #d4d4d8; }
    main { display: grid; grid-template-columns: minmax(0, 1fr) 320px; gap: 14px; padding: 14px; }
    .bar, .panel, .card, .feed { border: 1px solid #30343b; border-radius: 8px; background: #111418; }
    .bar { margin: 14px; padding: 14px; display: grid; grid-template-columns: 1.5fr repeat(5, minmax(90px, 1fr)); gap: 10px; align-items: center; }
    .status { font-size: 28px; font-weight: 900; overflow-wrap: anywhere; }
    .label { color: #8d95a3; font-size: 11px; text-transform: uppercase; font-weight: 800; }
    .value { font-weight: 850; overflow-wrap: anywhere; }
    .ok { color: #39d98a; border-color: #247c52; }
    .warn { color: #f4b740; border-color: #8a6420; }
    .bad { color: #ff5c66; border-color: #8f2029; }
    .purple { color: #c084fc; border-color: #6d28d9; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }
    .card { min-height: 268px; padding: 14px; border-top: 3px solid #6d28d9; }
    .card.paper { border-top-color: #39d98a; }
    .card.armed_dry_run { border-top-color: #f4b740; }
    .card.tiny_live { border-top-color: #ff5c66; }
    .lane-title { display: flex; justify-content: space-between; gap: 8px; align-items: start; }
    .big { font-size: 22px; font-weight: 950; }
    .pill { display: inline-block; margin: 4px 4px 0 0; padding: 5px 8px; border-radius: 999px; background: #191d23; border: 1px solid #343a45; font-size: 12px; font-weight: 850; }
    .cmd { width: 100%; min-height: 42px; margin-top: 8px; border: 1px solid #3b4250; border-radius: 7px; background: #181c22; color: #f5f7fb; font-weight: 850; cursor: pointer; }
    .cmd:hover { border-color: #d6a23b; }
    .sidebar { display: grid; gap: 14px; align-content: start; }
    .panel, .feed { padding: 14px; }
    .sacred { border-color: #7f1d1d; background: linear-gradient(180deg, #1a0b0c, #111418); }
    .eye { width: 150px; height: 68px; margin: 8px auto 12px; border: 3px solid #ef4444; border-radius: 50%; display: grid; place-items: center; box-shadow: 0 0 24px rgba(239,68,68,.35); }
    .eye::before { content: ""; width: 38px; height: 38px; border-radius: 50%; background: radial-gradient(circle, #fee2e2 0 14%, #ef4444 15% 48%, #450a0a 49%); border: 2px solid #fecaca; }
    .read-only { color: #fecaca; font-weight: 950; text-align: center; }
    .split { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 10px; }
    .feed-list { display: grid; gap: 8px; }
    .feed-row { border-left: 3px solid #3b4250; padding-left: 9px; }
    pre { white-space: pre-wrap; word-break: break-word; max-height: 220px; overflow: auto; background: #080a0d; border-radius: 7px; padding: 10px; border: 1px solid #27272a; }
    @media (max-width: 980px) { main { grid-template-columns: 1fr; } .bar { grid-template-columns: 1fr 1fr; } }
    @media (max-width: 560px) { .bar { grid-template-columns: 1fr; } h1 { font-size: 28px; } }
  </style>
</head>
<body>
  <header>
    <h1>Hammer Control Tower</h1>
    <div class="label">Autonomous lane cockpit · read only · no execution controls</div>
  </header>
  <section id="globalBar" class="bar bad">
    <div><div class="label">Global Safety</div><div id="globalStatus" class="status">LOADING</div></div>
    <div><div class="label">order_placed</div><div id="orderPlaced" class="value">false</div></div>
    <div><div class="label">network_allowed</div><div id="networkAllowed" class="value">false</div></div>
    <div><div class="label">secrets_shown</div><div id="secretsShown" class="value">false</div></div>
    <div><div class="label">kill switch</div><div id="killSwitch" class="value">loading</div></div>
    <div><button class="cmd" onclick="loadState()">Refresh</button></div>
  </section>
  <main>
    <section>
      <div id="lanes" class="grid"></div>
      <section class="feed" style="margin-top:14px">
        <h2>Bottom Feed</h2>
        <div id="feed" class="feed-list"></div>
      </section>
    </section>
    <aside class="sidebar">
      <section class="panel sacred">
        <h2>Sacred Gate Panel</h2>
        <div class="eye" aria-hidden="true"></div>
        <div id="gateStatus" class="status bad">LOADING</div>
        <div class="read-only">READ ONLY · NO ORDER BUTTON</div>
        <button id="gateCommand" class="cmd">Copy gate check command</button>
      </section>
      <section class="panel">
        <h2>Next Safest Action</h2>
        <div id="nextPrimary" class="big">loading</div>
        <p id="nextWhy"></p>
        <div class="label">Phase target</div>
        <div id="phaseTarget" class="value">loading</div>
        <button id="nextCommand" class="cmd">Copy safe command</button>
      </section>
      <section class="panel">
        <h2>Command Pack</h2>
        <div id="commands"></div>
      </section>
      <section class="panel">
        <h2>State</h2>
        <pre id="raw">loading</pre>
      </section>
    </aside>
  </main>
  <script>
    let currentState = null;
    function esc(value) {
      return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    }
    function tone(status) {
      const text = String(status || '').toUpperCase();
      if (text.includes('SAFE') || text.includes('READY')) return 'ok';
      if (text.includes('REVIEW') || text.includes('PREVIEW') || text.includes('DRY')) return 'warn';
      if (text.includes('TINY')) return 'bad';
      return 'bad';
    }
    function copyText(text) {
      navigator.clipboard.writeText(text || '');
    }
    function pills(items) {
      return (items || []).slice(0, 5).map(item => `<span class="pill">${esc(item)}</span>`).join('') || '<span class="pill">none</span>';
    }
    function renderLanes(lanes) {
      document.getElementById('lanes').innerHTML = (lanes || []).map(lane => `
        <article class="card ${esc(lane.current_mode)}">
          <div class="lane-title">
            <div><div class="big">${esc(lane.symbol)} · ${esc(lane.timeframe)} · ${esc(lane.direction)}</div><div class="label">${esc(lane.entry_mode)}</div></div>
            <span class="pill">${esc(lane.current_mode)}</span>
          </div>
          <div class="split">
            <div><div class="label">Lane status</div><div class="value ${tone(lane.lane_status)}">${esc(lane.lane_status)}</div></div>
            <div><div class="label">Freshness</div><div class="value">${esc(lane.freshness_window_seconds)}s</div></div>
            <div><div class="label">Latest route</div><div class="value">${esc(lane.latest_route_status)}</div></div>
            <div><div class="label">Autonomy</div><div class="value">${esc(lane.autonomy_decision_summary?.autonomy_decision || lane.autonomy_decision_summary?.status || 'n/a')}</div></div>
            <div><div class="label">Paper proof</div><div class="value">${esc(lane.paper_proof_summary?.matched)}</div></div>
            <div><div class="label">Tiny gate</div><div class="value ${tone(lane.tiny_live_gate_status)}">${esc(lane.tiny_live_gate_status)}</div></div>
          </div>
          <div style="margin-top:10px"><div class="label">Top blockers</div>${pills(lane.top_blockers)}</div>
          <div style="margin-top:10px"><div class="label">Next action</div><div class="value">${esc(lane.next_action)}</div></div>
        </article>`).join('');
    }
    function renderFeed(state) {
      const rows = [
        ['router', state.router_summary?.status, `${state.router_summary?.routed_count || 0} routed · ${state.router_summary?.blocked_count || 0} blocked`],
        ['scheduler', state.scheduler_summary?.status, `${state.scheduler_summary?.decisions_count || 0} decisions`],
        ['paper integration', state.paper_executor_summary?.status, `${state.paper_executor_summary?.recent_integrations_count || 0} recent records`],
        ['boundary', state.adapter_boundary_summary?.status, (state.adapter_boundary_summary?.main_blockers || []).join('; ') || 'no blockers reported'],
        ['recent blockers', state.global_safety?.status, (state.global_safety?.top_blockers || []).join('; ') || 'none']
      ];
      document.getElementById('feed').innerHTML = rows.map(row => `<div class="feed-row"><div class="label">${esc(row[0])}</div><div class="value ${tone(row[1])}">${esc(row[1])}</div><div>${esc(row[2])}</div></div>`).join('');
    }
    function renderCommands(pack) {
      document.getElementById('commands').innerHTML = Object.entries(pack || {}).map(([name, command]) => `<button class="cmd" title="${esc(command)}" onclick='copyText(${JSON.stringify(command)})'>${esc(name)}</button>`).join('');
    }
    async function loadState() {
      try {
        const response = await fetch('/operator/lane-cockpit/state');
        currentState = await response.json();
      } catch (error) {
        currentState = {
          status: 'LANE_COCKPIT_DEGRADED',
          read_only: true,
          no_order_buttons: true,
          global_safety: {status: 'SYSTEM REVIEW', order_placed: false, network_allowed: false, secrets_shown: false, global_kill_switch_status: 'UNKNOWN'},
          lanes: [],
          tiny_live_gate_summary: {status: 'DEGRADED'},
          next_action: {primary: 'Refresh cockpit state', why: 'State fetch failed; remain read-only.', safe_command: 'PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward lane-control-cockpit-state', phase_target: 'R133 repair'},
          command_pack: {},
          safety: {order_placed:false, real_order_placed:false, execution_attempted:false, order_payload_created:false, network_allowed:false, secrets_shown:false, paper_live_separation_intact:true, env_mutated:false, config_written:false, global_live_flags_changed:false, binance_order_endpoint_called:false, signed_request_created:false}
        };
      }
      const state = currentState;
      const global = state.global_safety || {};
      document.getElementById('globalStatus').textContent = global.status || state.status;
      document.getElementById('globalBar').className = `bar ${tone(global.status)}`;
      document.getElementById('orderPlaced').textContent = String(global.order_placed === true);
      document.getElementById('networkAllowed').textContent = String(global.network_allowed === true);
      document.getElementById('secretsShown').textContent = String(global.secrets_shown === true);
      document.getElementById('killSwitch').textContent = global.global_kill_switch_status || 'UNKNOWN';
      renderLanes(state.lanes);
      renderFeed(state);
      document.getElementById('gateStatus').textContent = state.tiny_live_gate_summary?.status || 'UNKNOWN';
      document.getElementById('gateStatus').className = `status ${tone(state.tiny_live_gate_summary?.status)}`;
      document.getElementById('nextPrimary').textContent = state.next_action?.primary || 'Inspect cockpit state';
      document.getElementById('nextWhy').textContent = state.next_action?.why || '';
      document.getElementById('phaseTarget').textContent = state.next_action?.phase_target || 'R134 later';
      document.getElementById('gateCommand').onclick = () => copyText(state.command_pack?.['first-tiny-live-lane-execution-gate'] || '');
      document.getElementById('nextCommand').onclick = () => copyText(state.next_action?.safe_command || '');
      renderCommands(state.command_pack);
      document.getElementById('raw').textContent = JSON.stringify(state, null, 2);
    }
    loadState();
    setInterval(loadState, 10000);
  </script>
</body>
</html>"""


def format_lane_control_cockpit_state_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _safe_source(name: str, failures: list[dict[str, str]], fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        value = fn()
        return dict(value) if isinstance(value, Mapping) else {"status": "SOURCE_INVALID", "value": value}
    except Exception as exc:  # pragma: no cover - exercised through monkeypatch tests
        failures.append({"source": name, "error_type": exc.__class__.__name__})
        return {"status": "SOURCE_FAILED", "source": name, "error_type": exc.__class__.__name__, "safety": dict(COCKPIT_SAFETY)}


def _select_lane_card(lanes: list[Mapping[str, Any]], lane_key: str) -> dict[str, Any]:
    for lane in lanes:
        if lane.get("lane_key") == lane_key:
            return dict(lane)
    return dict(lanes[0]) if lanes else {"lane_key": lane_key, "read_only": True, "no_order_buttons": True, "safety": dict(COCKPIT_SAFETY)}


def _latest_route_for_lane(router_status: Mapping[str, Any], lane_key: str) -> dict[str, Any] | None:
    for key in ("routed_candidates", "blocked_candidates", "expired_candidates"):
        for row in router_status.get(key, []) or []:
            if isinstance(row, Mapping) and str(row.get("lane_key") or "") == lane_key:
                return dict(row)
    return None


def _source_lane_matches(source: Mapping[str, Any], lane_key: str) -> bool:
    lane = source.get("lane") if isinstance(source.get("lane"), Mapping) else {}
    return str(source.get("lane_key") or lane.get("lane_key") or "") == lane_key


def _paper_proof_matched(tiny_gate: Mapping[str, Any], authorization: Mapping[str, Any]) -> bool:
    gate_proof = tiny_gate.get("paper_proof") if isinstance(tiny_gate.get("paper_proof"), Mapping) else {}
    prereqs = authorization.get("prerequisites") if isinstance(authorization.get("prerequisites"), Mapping) else {}
    auth_proof = prereqs.get("paper_proof_summary") if isinstance(prereqs.get("paper_proof_summary"), Mapping) else {}
    return bool(gate_proof.get("matched") or auth_proof.get("matched"))


def _lane_next_action(*, mode: str, lane_status: str, blockers: list[str], tiny_gate: Mapping[str, Any], adapter_boundary: Mapping[str, Any]) -> str:
    if blockers:
        return blockers[0]
    if mode == "paper":
        return "Keep collecting autonomous paper proof."
    if mode == "armed_dry_run":
        return "Inspect R126/R132 tiny-live readiness."
    if mode == "tiny_live" and tiny_gate.get("status") != TINY_LIVE_EXECUTION_READY:
        return "Tiny-live lane remains blocked by gate review."
    if adapter_boundary.get("status") != LIVE_ADAPTER_BOUNDARY_REVIEW_READY:
        return "Clear live adapter boundary review before R134."
    return f"Lane is {lane_status}; continue read-only monitoring."


def _router_summary(router: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": router.get("status"),
        "candidate_source": router.get("candidate_source"),
        "candidates_seen_count": router.get("candidates_seen_count", 0),
        "routed_count": router.get("routed_count", 0),
        "blocked_count": router.get("blocked_count", 0),
        "expired_count": router.get("expired_count", 0),
        "top_blockers": router.get("top_blockers", []),
        "safety": dict(COCKPIT_SAFETY),
    }


def _scheduler_summary(scheduler: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": scheduler.get("status"),
        "lanes_evaluated_count": scheduler.get("lanes_evaluated_count", 0),
        "candidates_seen_count": scheduler.get("candidates_seen_count", 0),
        "decisions_count": scheduler.get("decisions_count", len(scheduler.get("decisions") or [])),
        "tick_recorded": bool(scheduler.get("tick_recorded")),
        "rejection_reason": scheduler.get("rejection_reason"),
        "safety": dict(COCKPIT_SAFETY),
    }


def _paper_summary(status: Mapping[str, Any], preview: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": status.get("status"),
        "preview_status": preview.get("status"),
        "recent_integrations_count": len(status.get("recent_integrations") or []),
        "paper_execution_preview_count": len(preview.get("paper_execution_previews") or []),
        "integration_summary": status.get("integration_summary") or {},
        "safety": dict(COCKPIT_SAFETY),
    }


def _tiny_gate_summary(gate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": gate.get("status"),
        "lane_key": (gate.get("lane") or {}).get("lane_key") if isinstance(gate.get("lane"), Mapping) else gate.get("lane_key"),
        "paper_proof": gate.get("paper_proof") or {},
        "blockers": list(gate.get("blockers") or [])[:8],
        "next_actions": list(gate.get("next_actions") or [])[:6],
        "safety": dict(COCKPIT_SAFETY),
    }


def _authorization_summary(authorization: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": authorization.get("status"),
        "lane_key": authorization.get("lane_key"),
        "authorization_recorded": bool(authorization.get("authorization_recorded")),
        "config_written": False,
        "blockers": list(authorization.get("blockers") or [])[:8],
        "next_actions": list(authorization.get("next_actions") or [])[:6],
        "safety": dict(COCKPIT_SAFETY),
    }


def _kill_switch_summary(kill_switch: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": kill_switch.get("status"),
        "lane_key": kill_switch.get("lane_key"),
        "current_lane_mode": kill_switch.get("current_lane_mode"),
        "kill_switch_verdict": kill_switch.get("kill_switch_verdict") or {},
        "current_blockers": list(kill_switch.get("current_blockers") or [])[:8],
        "next_actions": list(kill_switch.get("next_actions") or [])[:6],
        "safety": dict(COCKPIT_SAFETY),
    }


def _adapter_boundary_summary(boundary: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": boundary.get("status"),
        "lane_key": boundary.get("lane_key"),
        "main_blockers": list(boundary.get("main_blockers") or [])[:8],
        "future_dry_authorization_requirements": list(boundary.get("future_dry_authorization_requirements") or [])[:8],
        "next_actions": list(boundary.get("next_actions") or [])[:6],
        "safety": dict(COCKPIT_SAFETY),
    }


def _kill_switch_label(kill_switch: Mapping[str, Any]) -> str:
    verdict = kill_switch.get("kill_switch_verdict") if isinstance(kill_switch.get("kill_switch_verdict"), Mapping) else {}
    if verdict.get("global_kill_switch_blocks_live_intent") is True:
        return "GLOBAL KILL BLOCKS LIVE INTENT"
    return str(kill_switch.get("status") or "UNKNOWN")


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _sanitize(payload: Any) -> Any:
    if isinstance(payload, Mapping):
        return {str(key): _sanitize(value) for key, value in payload.items()}
    if isinstance(payload, list):
        return [_sanitize(item) for item in payload]
    if isinstance(payload, tuple):
        return [_sanitize(item) for item in payload]
    if isinstance(payload, Path):
        return str(payload)
    if isinstance(payload, datetime):
        return payload.isoformat()
    return payload


def _html_escape(value: object) -> str:
    return html.escape(str(value or ""), quote=True)
