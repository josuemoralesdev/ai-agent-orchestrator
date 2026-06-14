You are in repo:
/home/josue/workspace/kernel/ai-agent-orchestrator-main

Follow:
- AGENTS.md
- codex_tasks/CODEX_RULES.md
- docs/hammer_radar/live_readiness/PHASE_INDEX.md
- docs/hammer_radar/live_readiness/TINY_LIVE_REAL_SUBMIT_OPERATOR_RUNBOOK.md

PHASE:
R260 Tiny-Live Fresh Cycle One-Shot Orchestrator

BRANCH:
r260-tiny-live-fresh-cycle-one-shot-orchestrator

PHASE CLASSIFICATION:
Primary: FRESH CYCLE ORCHESTRATION / PRE-LIVE COMPRESSION
Secondary: READONLY REFRESH, REGENERATION, SUBMIT PREVIEW, DRY GATE, MANUAL CHECKPOINT
Duplicate risk: EXTREME

WHY THIS PHASE EXISTS:
R259 Tiny-Live Fresh Cycle Checkpoint has been committed.

R259 confirmed the current required next step:
- RUN_R253_READONLY_REFRESH

R259 also confirmed the system remains blocked by:
- signed_request_timestamp_stale
- official_lane_not_tiny_live
- live_execution_not_enabled

The prior flow required the operator to manually run:
1. R253 final readonly refresh
2. R253B fresh signed request regeneration
3. R254 submit gate preview
4. R255 dry preview
5. R258 manual checkpoint re-check

That is safe but too fragmented.

R260 must compress that entire fresh cycle into one controlled orchestration command.

This phase may:
- call public readonly Binance endpoints through the existing R253 logic, only under exact confirmation
- regenerate fresh local signed requests through existing R253B logic, only under exact confirmation
- record R254 submit preview
- record R255 dry preview
- record R258 manual checkpoint re-check
- produce a final fresh-cycle go/no-go packet

This phase must NOT:
- submit
- call Binance order endpoint
- place any order
- arm live controls
- mutate lane controls
- mutate risk config
- bypass existing safety gates

This phase is the new compact bridge to live readiness.
It replaces manual hunting for five separate commands.

OFFICIAL LANE:
BTCUSDT|8m|short|ladder_close_50_618

HARD SAFETY RULE:
R260 is allowed to orchestrate existing safe steps.
R260 is NOT allowed to submit.

ALLOWED INSIDE R260 AFTER EXACT CONFIRMATION:
1. Public readonly Binance refresh:
   - GET /fapi/v1/exchangeInfo
   - GET /fapi/v1/premiumIndex?symbol=BTCUSDT
2. Fresh local stop/TP rebuild from R253 context.
3. Fresh local executable payload rebuild.
4. Fresh local signed request regeneration from runtime credential source.
5. R254 submit gate preview record.
6. R255 actual submit gate dry preview record.
7. R258 manual checkpoint re-check record.
8. R260 one-shot orchestration ledger record.

FORBIDDEN INSIDE R260:
- POST /fapi/v1/order
- POST /fapi/v1/batchOrders
- GET /fapi/v2/account
- GET /fapi/v3/account
- Any private/signed Binance endpoint except local HMAC creation for artifacts
- Any real submit
- Any order placement
- Any live-control mutation
- Any lane_controls.json write
- Any risk contract config write
- Any kill-switch disable
- Any global live flag change
- Any .env write
- Any external credential file write
- Any secret printing
- Any secret persistence
- Any paper/live separation violation

EXACT CONFIRMATION PHRASE:
I CONFIRM TINY LIVE FRESH CYCLE ONE-SHOT ORCHESTRATION ONLY; REFRESH READONLY MARKET, REGENERATE LOCAL SIGNED REQUEST, RECORD PREVIEWS; NO SUBMIT; NO ORDER; NO BINANCE ORDER CALL.

CAPABILITY SCAN FIRST:
Inspect:
- src/app/hammer_radar/operator/tiny_live_fresh_cycle_checkpoint.py
- src/app/hammer_radar/operator/tiny_live_manual_submit_checkpoint.py
- src/app/hammer_radar/operator/tiny_live_final_pre_submit_arming_drill.py
- src/app/hammer_radar/operator/tiny_live_operator_real_submit_runbook.py
- src/app/hammer_radar/operator/tiny_live_actual_submit_gate.py
- src/app/hammer_radar/operator/tiny_live_submit_gate_preview.py
- src/app/hammer_radar/operator/tiny_live_fresh_context_signed_request_regeneration_gate.py
- src/app/hammer_radar/operator/tiny_live_final_readonly_mark_price_refresh_gate.py
- src/app/hammer_radar/operator/tiny_live_submit_readiness_preview.py
- src/app/hammer_radar/operator/tiny_live_signed_request_runtime_source_write_gate.py
- src/app/hammer_radar/operator/tiny_live_signed_request_write_gate.py
- src/app/hammer_radar/operator/tiny_live_executable_payload_write_gate.py
- src/app/hammer_radar/operator/tiny_live_stop_take_profit_source_gate.py
- src/app/hammer_radar/operator/inspect.py
- src/app/hammer_radar/operator/*checkpoint* files
- src/app/hammer_radar/operator/*submit* files
- src/app/hammer_radar/operator/*fresh* files
- src/app/hammer_radar/operator/*readonly* files
- src/app/hammer_radar/operator/*signed* files
- src/app/hammer_radar/operator/*credential* files
- src/app/hammer_radar/operator/*live* files
- src/app/hammer_radar/operator/*lane* files
- src/app/hammer_radar/operator/*risk* files

Inspect configs read-only:
- configs/hammer_radar/tiny_live_risk_contracts.json
- configs/hammer_radar/lane_controls.json
- configs/hammer_radar/*.json

Inspect ledgers/logs:
- logs/hammer_radar_forward/tiny_live_fresh_cycle_checkpoint.ndjson
- logs/hammer_radar_forward/tiny_live_manual_submit_checkpoint.ndjson
- logs/hammer_radar_forward/tiny_live_final_pre_submit_arming_drill.ndjson
- logs/hammer_radar_forward/tiny_live_operator_real_submit_runbook.ndjson
- logs/hammer_radar_forward/tiny_live_actual_submit_gate.ndjson
- logs/hammer_radar_forward/tiny_live_submit_gate_preview.ndjson
- logs/hammer_radar_forward/tiny_live_fresh_context_signed_request_regeneration_gate.ndjson
- logs/hammer_radar_forward/tiny_live_final_readonly_mark_price_refresh_gate.ndjson
- logs/hammer_radar_forward/tiny_live_signed_request_write_gate.ndjson
- logs/hammer_radar_forward/tiny_live_executable_payload_write_gate.ndjson
- logs/hammer_radar_forward/tiny_live_stop_take_profit_source_gate.ndjson

Inspect docs:
- docs/hammer_radar/live_readiness/R259_TINY_LIVE_FRESH_CYCLE_CHECKPOINT.md
- docs/hammer_radar/live_readiness/R258_TINY_LIVE_MANUAL_SUBMIT_CHECKPOINT.md
- docs/hammer_radar/live_readiness/R257_TINY_LIVE_FINAL_PRE_SUBMIT_ARMING_DRILL.md
- docs/hammer_radar/live_readiness/R256_TINY_LIVE_OPERATOR_REAL_SUBMIT_RUNBOOK_AND_RECONCILIATION.md
- docs/hammer_radar/live_readiness/TINY_LIVE_REAL_SUBMIT_OPERATOR_RUNBOOK.md
- docs/hammer_radar/live_readiness/R255_TINY_LIVE_ACTUAL_SUBMIT_GATE.md
- docs/hammer_radar/live_readiness/R254_TINY_LIVE_SUBMIT_GATE_PREVIEW.md
- docs/hammer_radar/live_readiness/R253B_TINY_LIVE_FRESH_CONTEXT_SIGNED_REQUEST_REGENERATION_GATE.md
- docs/hammer_radar/live_readiness/R253_TINY_LIVE_FINAL_READONLY_MARK_PRICE_REFRESH_GATE.md
- docs/hammer_radar/live_readiness/PHASE_INDEX.md

REUSE / EXTEND:
Reuse existing modules. Do not duplicate logic unless necessary:
- R253 readonly refresh builder/fetcher
- R253B regeneration builder
- R254 submit gate preview builder
- R255 actual submit dry preview builder
- R258 manual checkpoint builder
- R259 fresh cycle checkpoint builder
- existing safety helpers
- existing NDJSON append helpers

Do not bypass the existing modules.
R260 should orchestrate them and validate their outputs.

REQUIRED MODULE:
Create:
src/app/hammer_radar/operator/tiny_live_fresh_cycle_one_shot_orchestrator.py

Expose:
- build_tiny_live_fresh_cycle_one_shot_orchestrator
- load_latest_tiny_live_fresh_cycle_checkpoint
- run_or_preview_r253_readonly_refresh_step
- run_or_preview_r253b_regeneration_step
- run_or_preview_r254_submit_gate_preview_step
- run_or_preview_r255_dry_preview_step
- run_or_preview_r258_manual_checkpoint_recheck_step
- build_one_shot_step_plan
- build_one_shot_step_results
- validate_one_shot_outputs
- build_one_shot_go_no_go_packet
- build_one_shot_operator_packet
- build_one_shot_safety_summary
- classify_tiny_live_fresh_cycle_one_shot_status
- append_tiny_live_fresh_cycle_one_shot_record
- load_tiny_live_fresh_cycle_one_shot_records
- summarize_tiny_live_fresh_cycle_one_shot_records

CLI:
Wire into inspect.py as:
tiny-live-fresh-cycle-one-shot

Args:
- --run-fresh-cycle-one-shot
- --record-fresh-cycle-one-shot
- --confirm-tiny-live-fresh-cycle-one-shot <phrase>

Preview only, no network/sign/regeneration:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-fresh-cycle-one-shot

Run fresh cycle, still no submit:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-fresh-cycle-one-shot \
  --run-fresh-cycle-one-shot \
  --record-fresh-cycle-one-shot \
  --confirm-tiny-live-fresh-cycle-one-shot "I CONFIRM TINY LIVE FRESH CYCLE ONE-SHOT ORCHESTRATION ONLY; REFRESH READONLY MARKET, REGENERATE LOCAL SIGNED REQUEST, RECORD PREVIEWS; NO SUBMIT; NO ORDER; NO BINANCE ORDER CALL."

Rejected:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-fresh-cycle-one-shot \
  --run-fresh-cycle-one-shot \
  --record-fresh-cycle-one-shot \
  --confirm-tiny-live-fresh-cycle-one-shot "wrong"

STATUS ENUM:
- TINY_LIVE_FRESH_CYCLE_ONE_SHOT_READY
- TINY_LIVE_FRESH_CYCLE_ONE_SHOT_RECORDED
- TINY_LIVE_FRESH_CYCLE_ONE_SHOT_REJECTED
- TINY_LIVE_FRESH_CYCLE_ONE_SHOT_BLOCKED
- TINY_LIVE_FRESH_CYCLE_ONE_SHOT_ERROR

OVERALL STATUS ENUM:
- TINY_LIVE_FRESH_CYCLE_ONE_SHOT_READY_FOR_CONFIRMATION
- TINY_LIVE_FRESH_CYCLE_ONE_SHOT_RECORDED_READY_FOR_LIVE_CONTROL_REVIEW
- TINY_LIVE_FRESH_CYCLE_ONE_SHOT_RECORDED_STILL_BLOCKED
- TINY_LIVE_FRESH_CYCLE_ONE_SHOT_REJECTED_BAD_CONFIRMATION
- TINY_LIVE_FRESH_CYCLE_ONE_SHOT_BLOCKED_BY_R253
- TINY_LIVE_FRESH_CYCLE_ONE_SHOT_BLOCKED_BY_R253B
- TINY_LIVE_FRESH_CYCLE_ONE_SHOT_BLOCKED_BY_R254
- TINY_LIVE_FRESH_CYCLE_ONE_SHOT_BLOCKED_BY_R255
- TINY_LIVE_FRESH_CYCLE_ONE_SHOT_BLOCKED_BY_R258
- UNKNOWN_NEEDS_MANUAL_REVIEW

OUTPUT MUST INCLUDE:
{
  "status": "...",
  "generated_at": "...",
  "run_fresh_cycle_one_shot_requested": false,
  "record_fresh_cycle_one_shot_requested": false,
  "confirmation_valid": false,
  "fresh_cycle_one_shot_recorded": false,
  "target_scope": {
    "official_lane_key": "BTCUSDT|8m|short|ladder_close_50_618",
    "symbol": "BTCUSDT",
    "timeframe": "8m",
    "direction": "short",
    "fresh_cycle_one_shot_only": true,
    "submit_allowed": false,
    "order_placed": false,
    "binance_order_endpoint_called": false,
    "network_allowed": false
  },
  "input_summary": {
    "r259_fresh_cycle_checkpoint_found": true/false,
    "r259_fresh_cycle_checkpoint_valid": true/false,
    "fresh_cycle_required": true/false
  },
  "one_shot_step_plan": {
    "steps": [
      "R253_READONLY_REFRESH",
      "R253B_REGENERATION",
      "R254_SUBMIT_GATE_PREVIEW",
      "R255_DRY_PREVIEW",
      "R258_MANUAL_CHECKPOINT_RECHECK"
    ],
    "will_call_public_readonly_binance": true/false,
    "will_sign_locally": true/false,
    "will_submit": false,
    "will_place_order": false,
    "requires_confirmation": true
  },
  "one_shot_step_results": {
    "r253_readonly_refresh": {
      "attempted": true/false,
      "succeeded": true/false,
      "fresh_mark_price": null,
      "blocked_by": []
    },
    "r253b_regeneration": {
      "attempted": true/false,
      "succeeded": true/false,
      "signed_requests_count": null,
      "blocked_by": []
    },
    "r254_submit_gate_preview": {
      "attempted": true/false,
      "succeeded": true/false,
      "blocked_by": []
    },
    "r255_dry_preview": {
      "attempted": true/false,
      "succeeded": true/false,
      "blocked_by": []
    },
    "r258_manual_checkpoint_recheck": {
      "attempted": true/false,
      "succeeded": true/false,
      "blocked_by": []
    }
  },
  "one_shot_output_validation": {
    "valid": true/false,
    "fresh_signed_request_available": true/false,
    "signed_request_fresh_enough_for_dry_preview": true/false,
    "submit_gate_preview_recorded": true/false,
    "dry_preview_recorded": true/false,
    "manual_checkpoint_rechecked": true/false,
    "errors": [],
    "warnings": []
  },
  "one_shot_go_no_go_packet": {
    "go_for_manual_submit_now": false,
    "go_for_live_control_review": true/false,
    "go_for_r260_to_r261_ui": true/false,
    "next_required_step": "LIVE_CONTROL_REVIEW|R261_UI_ARMING|R253_REFRESH_AGAIN|FIX_BLOCKER|WAIT",
    "operator_should_submit_now": false,
    "operator_should_arm_live_controls_manually": true/false
  },
  "one_shot_operator_packet": {
    "operator_should_review_fresh_cycle_result": true,
    "operator_should_not_submit_from_r260": true,
    "operator_should_run_live_control_review_next": true/false,
    "operator_should_open_ui_when_available": true/false,
    "manual_decision_required": true
  },
  "one_shot_checkpoint_matrix": {
    "r259_available": true/false,
    "fresh_cycle_required": true/false,
    "r253_succeeded": true/false,
    "r253b_succeeded": true/false,
    "r254_succeeded": true/false,
    "r255_dry_preview_succeeded": true/false,
    "r258_recheck_succeeded": true/false,
    "submit_allowed": false,
    "order_placed": false,
    "blocked_by": []
  },
  "fresh_cycle_one_shot_overall_status": "...",
  "recommended_next_operator_move": "...",
  "recommended_next_engineering_move": "...",
  "do_not_run_yet": [
    "real submit from R260",
    "real submit before live-control review",
    "real submit before R255 dry preview",
    "duplicate live submit"
  ],
  "safety": {...}
}

SAFETY OBJECT MUST INCLUDE:
- env_written=false
- env_mutated=false
- external_env_file_written=false
- config_written=false
- risk_contract_config_written=false
- lane_controls_written=false
- live_config_written=false
- fresh_cycle_one_shot_only=true
- hmac_signature_created=true only if R253B regeneration was actually run
- signed_request_written=true only if R253B regeneration was actually run
- signed_order_request_created=true only if R253B regeneration was actually run
- signed_trading_request_created=true only if R253B regeneration was actually run
- submit_allowed=false
- submit_attempted=false
- order_placed=false
- real_order_placed=false
- execution_attempted=false
- binance_order_endpoint_called=false
- binance_test_order_endpoint_called=false
- binance_account_endpoint_called=false
- binance_exchange_info_endpoint_called=true only if R253 readonly refresh was actually run
- binance_mark_price_endpoint_called=true only if R253 readonly refresh was actually run
- private_binance_endpoint_called=false
- signed_binance_endpoint_called=false
- network_allowed=true only for R253 public readonly refresh when confirmed
- transfer_endpoint_called=false
- withdraw_endpoint_called=false
- kill_switch_disabled=false
- live_controls_armed_by_phase=false
- secrets_shown=false
- secrets_persisted=false
- secret_values_in_output=false
- global_live_flags_changed=false
- paper_live_separation_intact=true
- official_tiny_live_lane_changed=false

LEDGER:
logs/hammer_radar_forward/tiny_live_fresh_cycle_one_shot.ndjson

Only append under exact confirmation phrase.

DOCS:
Create:
docs/hammer_radar/live_readiness/R260_TINY_LIVE_FRESH_CYCLE_ONE_SHOT_ORCHESTRATOR.md

Update:
docs/hammer_radar/live_readiness/TINY_LIVE_REAL_SUBMIT_OPERATOR_RUNBOOK.md

Update:
docs/hammer_radar/live_readiness/PHASE_INDEX.md

FUTURE TASKS:
Create:
codex_tasks/phases/R261_TINY_LIVE_CONTROLS_ARMING_UI_AND_API.md
codex_tasks/phases/R262_TINY_LIVE_FINAL_SUBMIT_CONSOLE.md
codex_tasks/phases/R263_TINY_LIVE_ACTUAL_SUBMIT_AND_IMMEDIATE_RECONCILIATION.md
codex_tasks/phases/R264_TINY_LIVE_POST_LIVE_HARDENING_AND_RECOVERY.md

R261:
- UI/API to review and intentionally arm tiny-live lane controls
- no submit

R262:
- UI/console final submit screen
- still no submit by default
- one-click/manual command display
- exact phrase awareness

R263:
- actual submit + immediate reconciliation
- exactly three orders
- post-submit exchange ids
- partial success handling

R264:
- post-live hardening/recovery
- abort/cancel orphan logic
- dashboard status
- re-entry lock

TESTS:
Create:
tests/hammer_radar/test_tiny_live_fresh_cycle_one_shot_orchestrator.py

Tests must cover:
- CLI exists and returns JSON
- preview does not network/sign/submit/order
- wrong confirmation rejects
- exact confirmation can orchestrate with monkeypatched R253/R253B/R254/R255/R258 calls
- one-shot blocks if R253 fails
- one-shot blocks if R253B fails
- one-shot blocks if R254 fails
- one-shot blocks if R255 dry preview fails
- one-shot blocks if R258 recheck fails
- no Binance order endpoint ever called
- public readonly endpoint only allowed through R253
- no submit
- no order
- no live-control mutation
- no env/config/lane_controls mutation
- no secret values in output

VALIDATION:
Run py_compile:
- src/app/hammer_radar/operator/tiny_live_fresh_cycle_one_shot_orchestrator.py
- src/app/hammer_radar/operator/inspect.py

Run focused test:
- tests/hammer_radar/test_tiny_live_fresh_cycle_one_shot_orchestrator.py

Run related tests:
- tests/hammer_radar/test_tiny_live_fresh_cycle_checkpoint.py
- tests/hammer_radar/test_tiny_live_manual_submit_checkpoint.py
- tests/hammer_radar/test_tiny_live_final_pre_submit_arming_drill.py
- tests/hammer_radar/test_tiny_live_actual_submit_gate.py
- tests/hammer_radar/test_tiny_live_submit_gate_preview.py
- tests/hammer_radar/test_tiny_live_fresh_context_signed_request_regeneration_gate.py
- tests/hammer_radar/test_tiny_live_final_readonly_mark_price_refresh_gate.py

Run full:
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar

SMOKE:
Preview:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-fresh-cycle-one-shot \
  | jq '.status, .target_scope, .input_summary, .one_shot_step_plan, .one_shot_step_results, .one_shot_output_validation, .one_shot_go_no_go_packet, .one_shot_operator_packet, .one_shot_checkpoint_matrix, .fresh_cycle_one_shot_overall_status, .recommended_next_operator_move, .recommended_next_engineering_move, .do_not_run_yet, .safety'

Run one-shot:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-fresh-cycle-one-shot \
  --run-fresh-cycle-one-shot \
  --record-fresh-cycle-one-shot \
  --confirm-tiny-live-fresh-cycle-one-shot "I CONFIRM TINY LIVE FRESH CYCLE ONE-SHOT ORCHESTRATION ONLY; REFRESH READONLY MARKET, REGENERATE LOCAL SIGNED REQUEST, RECORD PREVIEWS; NO SUBMIT; NO ORDER; NO BINANCE ORDER CALL." \
  | jq '.status, .fresh_cycle_one_shot_recorded, .one_shot_step_results, .one_shot_output_validation, .one_shot_go_no_go_packet, .one_shot_checkpoint_matrix, .fresh_cycle_one_shot_overall_status, .safety'

Rejected:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-fresh-cycle-one-shot \
  --run-fresh-cycle-one-shot \
  --record-fresh-cycle-one-shot \
  --confirm-tiny-live-fresh-cycle-one-shot "wrong" \
  | jq '.status, .confirmation_valid, .fresh_cycle_one_shot_recorded, .safety'

Secret leak check:
PYTHONPATH=. .venv/bin/python - <<'PY'
import os
from pathlib import Path

paths = [
    Path("logs/hammer_radar_forward/tiny_live_fresh_cycle_one_shot.ndjson"),
    Path("logs/hammer_radar_forward/tiny_live_signed_request_write_gate.ndjson"),
    Path("logs/hammer_radar_forward/tiny_live_fresh_context_signed_request_regeneration_gate.ndjson"),
]
raw = "\n".join(path.read_text() for path in paths if path.exists())

external = Path("/home/josue/.config/hammer-radar/binance-signing.env")
values = []
if external.exists():
    for line in external.read_text().splitlines():
        if line.startswith("BINANCE_API_KEY=") or line.startswith("BINANCE_API_SECRET="):
            _, value = line.split("=", 1)
            if value:
                values.append(value.strip())

for key in ("BINANCE_API_KEY", "BINANCE_API_SECRET"):
    value = os.environ.get(key)
    if value:
        values.append(value)

for value in values:
    if value and value in raw:
        raise SystemExit("SECRET_LEAK_DETECTED")

print("NO_SECRET_VALUES_FOUND")
PY

Mutation check:
git diff -- .env || true
git diff -- configs/hammer_radar/tiny_live_risk_contracts.json || true
git diff -- configs/hammer_radar/lane_controls.json || true
git diff -- logs/hammer_radar_forward/candles_BTCUSDT_8m.ndjson || true
git diff -- logs/hammer_radar_forward/paper_outcomes.ndjson || true
git diff -- logs/hammer_radar_forward/strategy_performance.ndjson || true
git diff -- logs/hammer_radar_forward/strategy_promotion_status.ndjson || true

Expected artifacts:
git status --short logs/hammer_radar_forward/tiny_live_fresh_cycle_one_shot.ndjson || true
git status --short logs/hammer_radar_forward/tiny_live_final_readonly_mark_price_refresh_gate.ndjson || true
git status --short logs/hammer_radar_forward/tiny_live_fresh_context_signed_request_regeneration_gate.ndjson || true
git status --short logs/hammer_radar_forward/tiny_live_submit_gate_preview.ndjson || true
git status --short logs/hammer_radar_forward/tiny_live_actual_submit_gate.ndjson || true
git status --short logs/hammer_radar_forward/tiny_live_manual_submit_checkpoint.ndjson || true

tail -n 3 logs/hammer_radar_forward/tiny_live_fresh_cycle_one_shot.ndjson 2>/dev/null || true

FINAL PHASE REPORT REQUIRED:
At the end, report:
- phase status
- files changed
- tests run
- smoke status
- safety status
- one_shot_step_plan
- one_shot_step_results
- one_shot_output_validation
- one_shot_go_no_go_packet
- one_shot_operator_packet
- one_shot_checkpoint_matrix
- fresh_cycle_one_shot_overall_status
- exact files mutated
- recommended next operator move
- recommended next engineering move
- do not commit
- do not run real submit

Aggressive mode:
Complete in one pass.
Compress the fresh cycle.
Do not mutate env/config/lane controls.
Do not write external secret files.
Do not print secrets.
Do not persist secrets.
Do not call Binance order/private/account endpoints.
Do not submit.
Do not place orders.
Only run public readonly refresh and local signing when exact confirmation command is explicitly run.
