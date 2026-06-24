#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="/home/josue/workspace/kernel/ai-agent-orchestrator-main"
cd "${REPO_ROOT}"

PYTHONPATH=. .venv/bin/python - <<'PY'
from __future__ import annotations

from src.app.hammer_radar.operator.paper_refresh_scheduler import scheduler_status
from src.app.hammer_radar.operator.strategy_lab_preview import build_strategy_lab_preview
from src.app.hammer_radar.operator.tiny_live_autonomous_trigger_scheduler_timer_health import (
    build_autonomous_trigger_scheduler_timer_health,
)
from src.app.hammer_radar.operator.tiny_live_final_authorization_gate import (
    build_status_tiny_live_final_authorization_gate,
)

LOG_DIR = "logs/hammer_radar_forward"

refresh = scheduler_status(log_dir=LOG_DIR)
last_run = refresh.get("last_run") or {}
timer = build_autonomous_trigger_scheduler_timer_health(log_dir=LOG_DIR)
gate = build_status_tiny_live_final_authorization_gate(log_dir=LOG_DIR)
lab = build_strategy_lab_preview(log_dir=LOG_DIR, write=False)

print("R304 PAPER REFRESH HEALTH")
print(f"paper_refresh_health_status: {last_run.get('paper_refresh_health_status') or refresh.get('paper_refresh_health_status')}")
print(f"runs_recorded: {refresh.get('runs_recorded')}")
print(f"last_run_id: {last_run.get('refresh_run_id')}")
print(f"last_completed: {len(last_run.get('completed_tasks') or [])}")
print(f"last_failed: {len(last_run.get('failed_tasks') or [])}")
print(f"last_failed_tasks: {','.join(last_run.get('failed_tasks') or []) or 'none'}")
print(f"last_health: {last_run.get('paper_refresh_health_status')}")
print()

print("R304 TIMER AND FINAL GATE")
print(f"timer_health_status: {timer.get('status')}")
print(f"timer_active: {timer.get('timer_active')}")
print(f"final_gate_status: {gate.get('status')}")
print(f"current_armed_lane: {gate.get('armed_lane_key') or gate.get('requested_lane_key')}")
print(f"current_candidate_lane: {gate.get('current_real_candidate_lane_key')}")
print(f"final_command_available: {gate.get('final_command_available')}")
print(f"submit_allowed: {gate.get('submit_allowed')}")
print()

print("R304 STRATEGY LAB TOP PREVIEW")
for row in lab.get("top_preview_candidates", [])[:8]:
    print(
        f"{row.get('lane_key')} | {row.get('watch_category')} | "
        f"samples={row.get('sample_count')} win={row.get('win_rate_pct')} "
        f"avg={row.get('avg_pnl_pct')} action={row.get('recommended_lab_action')}"
    )
if not lab.get("top_preview_candidates"):
    print("none")
print()

print("R304 BETRAYAL PREVIEW")
for row in lab.get("betrayal_preview_candidates", [])[:8]:
    print(
        f"{row.get('lane_key')} | samples={row.get('sample_count')} "
        f"win={row.get('win_rate_pct')} avg={row.get('avg_pnl_pct')} "
        f"decision={row.get('betrayal_gate_decision')}"
    )
if not lab.get("betrayal_preview_candidates"):
    print("none")
print()

print("R304 SAFETY FLAGS")
safety = lab.get("safety") or {}
for key in (
    "live_execution_enabled",
    "allow_live_orders",
    "global_kill_switch",
    "order_placed",
    "real_order_placed",
    "execution_attempted",
    "submit_allowed",
    "final_command_available",
    "binance_order_endpoint_called",
    "binance_test_order_endpoint_called",
    "secrets_shown",
):
    print(f"{key}: {safety.get(key)}")
PY
