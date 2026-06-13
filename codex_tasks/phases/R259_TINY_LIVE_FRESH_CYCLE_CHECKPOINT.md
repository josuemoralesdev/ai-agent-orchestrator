You are in repo:
/home/josue/workspace/kernel/ai-agent-orchestrator-main

Follow:
- AGENTS.md
- codex_tasks/CODEX_RULES.md
- docs/hammer_radar/live_readiness/PHASE_INDEX.md
- docs/hammer_radar/live_readiness/TINY_LIVE_REAL_SUBMIT_OPERATOR_RUNBOOK.md

PHASE:
R259 Tiny-Live Fresh Cycle Checkpoint

BRANCH:
r259-tiny-live-fresh-cycle-checkpoint

PHASE CLASSIFICATION:
Primary: FRESH CYCLE CHECKPOINT / PRE-MANUAL-SUBMIT COORDINATION
Secondary: READONLY/REGENERATION/DRY-PREVIEW ORCHESTRATION, NO-SUBMIT SAFETY
Duplicate risk: EXTREME

WHY THIS PHASE EXISTS:
R258 Tiny-Live Manual Submit Checkpoint has been committed.

R258 confirmed:
- manual submit checkpoint is available
- go_for_manual_submit_now=false
- next_required_human_action=RUN_FRESH_CYCLE
- fresh_cycle_required=true
- live_controls_manual_review_required=true
- current blockers:
  - signed_request_timestamp_stale
  - official_lane_not_tiny_live
  - live_execution_not_enabled

R259 must create a checkpoint that coordinates the required fresh cycle:
1. R253 final readonly refresh
2. R253B fresh signed request regeneration
3. R254 submit gate preview
4. R255 dry preview
5. R258 manual checkpoint re-check

R259 must NOT execute those steps automatically.
R259 must NOT call Binance.
R259 must NOT regenerate or sign.
R259 must NOT submit.
R259 must NOT arm live controls.
R259 is a checkpoint/orchestration packet only.

CORE INTENT:
Create a fresh cycle checkpoint that:
1. Reads latest R258 manual checkpoint.
2. Reads latest R257 final pre-submit arming drill.
3. Reads latest R256 runbook.
4. Reads latest R255 actual submit gate dry preview.
5. Reads latest R254 submit gate preview.
6. Reads latest R253B regeneration artifact.
7. Reads latest R253 final readonly refresh artifact.
8. Reads lane controls and risk contract read-only.
9. Determines whether each fresh-cycle step is missing, stale, blocked, or ready.
10. Produces a deterministic required next step.
11. Provides exact command templates for each required step, but does not run them.
12. Produces R260 future manual live-submit execution checkpoint placeholder.

This phase should make the operator see the fresh-cycle state in one command.

OFFICIAL LANE:
BTCUSDT|8m|short|ladder_close_50_618

CURRENT KNOWN BLOCKERS:
- signed_request_timestamp_stale
- official_lane_not_tiny_live
- live_execution_not_enabled

EXPECTED SAFE R259 RESULT:
- submit_allowed=false
- order_placed=false
- binance_order_endpoint_called=false
- network_allowed=false
- operator_should_submit_now=false
- operator_should_run_fresh_cycle=true
- operator_should_run_readonly_refresh_first=true if latest R253/R253B/R255 timestamps are stale
- operator_should_arm_live_controls_manually=true if controls still off
- final manual decision required

NON-NEGOTIABLES:
- No Binance calls.
- No network calls.
- No order endpoint.
- No test order endpoint.
- No account/private endpoint.
- No signed/private endpoint.
- No submit.
- No order placement.
- No HMAC signature creation.
- No signed request write.
- No regeneration.
- No API key loading.
- No API secret loading.
- No secrets printed.
- No secrets persisted.
- No .env write.
- No external env file write.
- No lane_controls.json write.
- No risk contract config write.
- No scheduler/fisherman config write.
- No kill switch disable.
- No global live flag changes.
- No paper_outcomes append.
- No strategy performance append.
- No strategy promotion status append.
- No betrayal promotion.
- No alternate lane promotion.
- No official lane change.
- No submit_allowed=true.
- No network_allowed=true.
- No auto-arm.
- No sudo.
- Do not commit.
- Do not merge.
- Do not tag.
- Do not touch or stage AGENTS.md.

ALLOWED:
- Read local ledgers/configs.
- Build fresh cycle checkpoint packet.
- Build command templates only.
- Append R259 checkpoint ledger under exact confirmation.
- Add docs/tests.
- Create R260 future task.

CONFIRMATION PHRASE:
I CONFIRM TINY LIVE FRESH CYCLE CHECKPOINT RECORDING ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL.

CAPABILITY SCAN FIRST:
Inspect:
- src/app/hammer_radar/operator/tiny_live_manual_submit_checkpoint.py
- src/app/hammer_radar/operator/tiny_live_final_pre_submit_arming_drill.py
- src/app/hammer_radar/operator/tiny_live_operator_real_submit_runbook.py
- src/app/hammer_radar/operator/tiny_live_actual_submit_gate.py
- src/app/hammer_radar/operator/tiny_live_submit_gate_preview.py
- src/app/hammer_radar/operator/tiny_live_fresh_context_signed_request_regeneration_gate.py
- src/app/hammer_radar/operator/tiny_live_final_readonly_mark_price_refresh_gate.py
- src/app/hammer_radar/operator/tiny_live_submit_readiness_preview.py
- src/app/hammer_radar/operator/inspect.py
- src/app/hammer_radar/operator/*checkpoint* files
- src/app/hammer_radar/operator/*submit* files
- src/app/hammer_radar/operator/*arming* files
- src/app/hammer_radar/operator/*runbook* files
- src/app/hammer_radar/operator/*reconcile* files
- src/app/hammer_radar/operator/*live* files
- src/app/hammer_radar/operator/*lane* files
- src/app/hammer_radar/operator/*risk* files
- src/app/hammer_radar/operator/*kill* files
- src/app/hammer_radar/operator/*signed* files
- src/app/hammer_radar/operator/*readonly* files

Inspect configs read-only:
- configs/hammer_radar/tiny_live_risk_contracts.json
- configs/hammer_radar/lane_controls.json
- configs/hammer_radar/*.json

Inspect ledgers/logs:
- logs/hammer_radar_forward/tiny_live_manual_submit_checkpoint.ndjson
- logs/hammer_radar_forward/tiny_live_final_pre_submit_arming_drill.ndjson
- logs/hammer_radar_forward/tiny_live_operator_real_submit_runbook.ndjson
- logs/hammer_radar_forward/tiny_live_actual_submit_gate.ndjson
- logs/hammer_radar_forward/tiny_live_submit_gate_preview.ndjson
- logs/hammer_radar_forward/tiny_live_fresh_context_signed_request_regeneration_gate.ndjson
- logs/hammer_radar_forward/tiny_live_final_readonly_mark_price_refresh_gate.ndjson
- logs/hammer_radar_forward/tiny_live_submit_readiness_preview.ndjson
- logs/hammer_radar_forward/tiny_live_signed_request_write_gate.ndjson
- logs/hammer_radar_forward/tiny_live_executable_payload_write_gate.ndjson
- logs/hammer_radar_forward/tiny_live_stop_take_profit_source_gate.ndjson

Inspect docs:
- docs/hammer_radar/live_readiness/R258_TINY_LIVE_MANUAL_SUBMIT_CHECKPOINT.md
- docs/hammer_radar/live_readiness/R257_TINY_LIVE_FINAL_PRE_SUBMIT_ARMING_DRILL.md
- docs/hammer_radar/live_readiness/R256_TINY_LIVE_OPERATOR_REAL_SUBMIT_RUNBOOK_AND_RECONCILIATION.md
- docs/hammer_radar/live_readiness/TINY_LIVE_REAL_SUBMIT_OPERATOR_RUNBOOK.md
- docs/hammer_radar/live_readiness/R255_TINY_LIVE_ACTUAL_SUBMIT_GATE.md
- docs/hammer_radar/live_readiness/R254_TINY_LIVE_SUBMIT_GATE_PREVIEW.md
- docs/hammer_radar/live_readiness/R253B_TINY_LIVE_FRESH_CONTEXT_SIGNED_REQUEST_REGENERATION_GATE.md
- docs/hammer_radar/live_readiness/R253_TINY_LIVE_FINAL_READONLY_MARK_PRICE_REFRESH_GATE.md
- docs/hammer_radar/live_readiness/PHASE_INDEX.md

Inspect tests:
- tests/hammer_radar/test_tiny_live_manual_submit_checkpoint.py
- tests/hammer_radar/test_tiny_live_final_pre_submit_arming_drill.py
- tests/hammer_radar/test_tiny_live_operator_real_submit_runbook.py
- tests/hammer_radar/test_tiny_live_actual_submit_gate.py
- tests/hammer_radar/test_tiny_live_submit_gate_preview.py
- tests/hammer_radar/test_tiny_live_fresh_context_signed_request_regeneration_gate.py
- tests/hammer_radar/test_tiny_live_final_readonly_mark_price_refresh_gate.py
- tests/hammer_radar/test_*checkpoint* if present
- tests/hammer_radar/test_*fresh* if present
- tests/hammer_radar/test_*submit* if present
- tests/hammer_radar/test_*live* if present

REUSE / EXTEND:
Reuse:
- R258 manual checkpoint loader/summaries.
- R257 arming drill summaries.
- R256 runbook summaries.
- R255 actual submit gate freshness/blocker summaries.
- R254 submit gate preview summaries.
- R253B regeneration summaries.
- R253 readonly refresh summaries.
- Existing safety conventions.
- Existing NDJSON append helpers.

Do not execute fresh cycle here.
Do not call Binance.
Do not sign.
Do not mutate controls.
Do not arm live controls.
Do not regenerate signed requests.
Do not submit.

REQUIRED MODULE:
Create:
src/app/hammer_radar/operator/tiny_live_fresh_cycle_checkpoint.py

Expose:
- build_tiny_live_fresh_cycle_checkpoint
- load_latest_tiny_live_manual_submit_checkpoint
- load_latest_tiny_live_final_pre_submit_arming_drill
- load_latest_tiny_live_operator_real_submit_runbook
- load_latest_tiny_live_actual_submit_gate
- load_latest_tiny_live_submit_gate_preview
- load_latest_tiny_live_fresh_context_signed_request_regeneration_gate
- load_latest_tiny_live_final_readonly_mark_price_refresh_gate
- summarize_fresh_cycle_inputs
- summarize_fresh_cycle_step_statuses
- summarize_fresh_cycle_blockers
- build_fresh_cycle_command_templates
- build_fresh_cycle_go_no_go_packet
- build_fresh_cycle_checkpoint_matrix
- classify_tiny_live_fresh_cycle_checkpoint_status
- append_tiny_live_fresh_cycle_checkpoint_record
- load_tiny_live_fresh_cycle_checkpoint_records
- summarize_tiny_live_fresh_cycle_checkpoint_records

CLI:
Wire into inspect.py as:
tiny-live-fresh-cycle-checkpoint

Args:
- --record-fresh-cycle-checkpoint
- --confirm-tiny-live-fresh-cycle-checkpoint <phrase>

Preview:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-fresh-cycle-checkpoint

Record:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-fresh-cycle-checkpoint \
  --record-fresh-cycle-checkpoint \
  --confirm-tiny-live-fresh-cycle-checkpoint "I CONFIRM TINY LIVE FRESH CYCLE CHECKPOINT RECORDING ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL."

Rejected:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-fresh-cycle-checkpoint \
  --record-fresh-cycle-checkpoint \
  --confirm-tiny-live-fresh-cycle-checkpoint "wrong"

STATUS ENUM:
- TINY_LIVE_FRESH_CYCLE_CHECKPOINT_READY
- TINY_LIVE_FRESH_CYCLE_CHECKPOINT_RECORDED
- TINY_LIVE_FRESH_CYCLE_CHECKPOINT_REJECTED
- TINY_LIVE_FRESH_CYCLE_CHECKPOINT_BLOCKED
- TINY_LIVE_FRESH_CYCLE_CHECKPOINT_ERROR

OVERALL STATUS ENUM:
- TINY_LIVE_FRESH_CYCLE_READY_FOR_RECORDING
- TINY_LIVE_FRESH_CYCLE_RECORDED_REFRESH_REQUIRED
- TINY_LIVE_FRESH_CYCLE_RECORDED_REGENERATION_REQUIRED
- TINY_LIVE_FRESH_CYCLE_RECORDED_DRY_PREVIEW_REQUIRED
- TINY_LIVE_FRESH_CYCLE_RECORDED_MANUAL_DECISION_REQUIRED
- TINY_LIVE_FRESH_CYCLE_REJECTED_BAD_CONFIRMATION
- TINY_LIVE_FRESH_CYCLE_BLOCKED_BY_MISSING_R258
- UNKNOWN_NEEDS_MANUAL_REVIEW

OUTPUT MUST INCLUDE:
{
  "status": "...",
  "generated_at": "...",
  "record_fresh_cycle_checkpoint_requested": false,
  "confirmation_valid": false,
  "fresh_cycle_checkpoint_recorded": false,
  "target_scope": {
    "official_lane_key": "BTCUSDT|8m|short|ladder_close_50_618",
    "symbol": "BTCUSDT",
    "timeframe": "8m",
    "direction": "short",
    "fresh_cycle_checkpoint_only": true,
    "submit_allowed": false,
    "order_placed": false,
    "binance_order_endpoint_called": false,
    "network_allowed": false
  },
  "input_summary": {
    "r258_manual_checkpoint_found": true/false,
    "r258_manual_checkpoint_valid": true/false,
    "r257_final_arming_found": true/false,
    "r256_runbook_found": true/false,
    "r255_actual_submit_gate_found": true/false,
    "r254_submit_gate_preview_found": true/false,
    "r253b_fresh_regeneration_found": true/false,
    "r253_final_readonly_found": true/false
  },
  "fresh_cycle_step_statuses": {
    "r253_final_readonly_refresh": {
      "available": true/false,
      "fresh_enough": true/false,
      "required_next": true/false
    },
    "r253b_fresh_signed_regeneration": {
      "available": true/false,
      "fresh_enough": true/false,
      "required_next": true/false
    },
    "r254_submit_gate_preview": {
      "available": true/false,
      "fresh_enough": true/false,
      "required_next": true/false
    },
    "r255_actual_submit_gate_dry_preview": {
      "available": true/false,
      "fresh_enough": true/false,
      "required_next": true/false
    },
    "r258_manual_checkpoint_recheck": {
      "available": true/false,
      "required_after_fresh_cycle": true
    }
  },
  "fresh_cycle_blockers": {
    "blocked_by": [],
    "timestamp_stale": true/false,
    "live_controls_not_armed": true/false,
    "live_execution_not_enabled": true/false,
    "manual_decision_required": true,
    "submit_allowed_now": false
  },
  "fresh_cycle_command_templates": {
    "r253_readonly_refresh_command": "...",
    "r253b_regeneration_command": "...",
    "r254_submit_gate_preview_command": "...",
    "r255_dry_preview_command": "...",
    "r258_recheck_command": "...",
    "commands_are_templates_only": true,
    "must_not_auto_run": true
  },
  "fresh_cycle_go_no_go_packet": {
    "go_for_manual_submit_now": false,
    "go_for_fresh_cycle_now": true/false,
    "next_required_step": "RUN_R253_READONLY_REFRESH|RUN_R253B_REGENERATION|RUN_R254_PREVIEW|RUN_R255_DRY_PREVIEW|RUN_R258_RECHECK|WAIT|FIX_BLOCKER",
    "operator_should_submit_now": false,
    "operator_should_arm_live_controls_manually": true/false,
    "operator_should_run_fresh_cycle": true/false
  },
  "fresh_cycle_checkpoint_matrix": {
    "r258_available": true/false,
    "fresh_cycle_required": true/false,
    "fresh_cycle_next_step_known": true/false,
    "command_templates_ready": true/false,
    "record_confirmed": true/false,
    "recorded": true/false,
    "submit_allowed": false,
    "order_placed": false,
    "blocked_by": []
  },
  "fresh_cycle_checkpoint_overall_status": "...",
  "recommended_next_operator_move": "...",
  "recommended_next_engineering_move": "...",
  "do_not_run_yet": [
    "real submit before fresh cycle",
    "real submit before R255 dry preview",
    "real submit while live controls are not intentionally armed",
    "duplicate live submit",
    "manual submit while blockers remain"
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
- fresh_cycle_checkpoint_only=true
- hmac_signature_created=false
- signed_request_written=false
- signed_order_request_created=false
- signed_trading_request_created=false
- submit_allowed=false
- submit_attempted=false
- order_placed=false
- real_order_placed=false
- execution_attempted=false
- binance_order_endpoint_called=false
- binance_test_order_endpoint_called=false
- binance_account_endpoint_called=false
- binance_exchange_info_endpoint_called=false
- binance_mark_price_endpoint_called=false
- private_binance_endpoint_called=false
- signed_binance_endpoint_called=false
- network_allowed=false
- transfer_endpoint_called=false
- withdraw_endpoint_called=false
- kill_switch_disabled=false
- live_controls_armed_by_phase=false
- secrets_read=false
- secrets_shown=false
- secrets_persisted=false
- secret_values_in_output=false
- global_live_flags_changed=false
- paper_live_separation_intact=true
- official_tiny_live_lane_changed=false

LEDGER:
logs/hammer_radar_forward/tiny_live_fresh_cycle_checkpoint.ndjson

Only append under exact confirmation phrase.

DOCS:
Create:
docs/hammer_radar/live_readiness/R259_TINY_LIVE_FRESH_CYCLE_CHECKPOINT.md

Update:
docs/hammer_radar/live_readiness/TINY_LIVE_REAL_SUBMIT_OPERATOR_RUNBOOK.md

Update:
docs/hammer_radar/live_readiness/PHASE_INDEX.md

FUTURE TASK:
Create:
codex_tasks/phases/R260_TINY_LIVE_MANUAL_LIVE_SUBMIT_EXECUTION_CHECKPOINT.md

R260 should:
- still not auto-submit
- be the manual live-submit execution checkpoint after a fresh cycle is complete
- verify fresh signed request age within seconds
- verify R255 dry preview is green
- verify live controls were intentionally armed by operator
- verify no duplicate live submit
- show final manual command
- require the user/operator to run live command outside Codex task only
- never auto-submit

TESTS:
Create:
tests/hammer_radar/test_tiny_live_fresh_cycle_checkpoint.py

Tests must cover:
- CLI exists and returns JSON
- preview writes no ledger
- wrong confirmation rejects
- exact confirmation records checkpoint only
- no Binance/network calls
- no signing
- no submit
- no order
- summarizes R258 blockers
- detects R253 readonly refresh is next when stale
- detects R253B regeneration needed when signed timestamp stale
- command templates exist
- command templates are template-only
- go_for_manual_submit_now=false
- no env/config/lane_controls mutation
- no secrets in output

VALIDATION:
Run py_compile:
- src/app/hammer_radar/operator/tiny_live_fresh_cycle_checkpoint.py
- src/app/hammer_radar/operator/inspect.py

Run focused test:
- tests/hammer_radar/test_tiny_live_fresh_cycle_checkpoint.py

Run related tests:
- tests/hammer_radar/test_tiny_live_manual_submit_checkpoint.py
- tests/hammer_radar/test_tiny_live_final_pre_submit_arming_drill.py
- tests/hammer_radar/test_tiny_live_operator_real_submit_runbook.py
- tests/hammer_radar/test_tiny_live_actual_submit_gate.py
- tests/hammer_radar/test_tiny_live_submit_gate_preview.py

Run full:
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar

SMOKE:
Preview:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-fresh-cycle-checkpoint \
  | jq '.status, .target_scope, .input_summary, .fresh_cycle_step_statuses, .fresh_cycle_blockers, .fresh_cycle_command_templates, .fresh_cycle_go_no_go_packet, .fresh_cycle_checkpoint_matrix, .fresh_cycle_checkpoint_overall_status, .recommended_next_operator_move, .recommended_next_engineering_move, .do_not_run_yet, .safety'

Record:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-fresh-cycle-checkpoint \
  --record-fresh-cycle-checkpoint \
  --confirm-tiny-live-fresh-cycle-checkpoint "I CONFIRM TINY LIVE FRESH CYCLE CHECKPOINT RECORDING ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL." \
  | jq '.status, .fresh_cycle_checkpoint_recorded, .fresh_cycle_go_no_go_packet, .fresh_cycle_checkpoint_matrix, .fresh_cycle_checkpoint_overall_status, .safety'

Rejected:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-fresh-cycle-checkpoint \
  --record-fresh-cycle-checkpoint \
  --confirm-tiny-live-fresh-cycle-checkpoint "wrong" \
  | jq '.status, .confirmation_valid, .fresh_cycle_checkpoint_recorded, .safety'

Secret leak check:
PYTHONPATH=. .venv/bin/python - <<'PY'
import os
from pathlib import Path

path = Path("logs/hammer_radar_forward/tiny_live_fresh_cycle_checkpoint.ndjson")
raw = path.read_text() if path.exists() else ""

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

Expected artifact:
git status --short logs/hammer_radar_forward/tiny_live_fresh_cycle_checkpoint.ndjson || true
tail -n 3 logs/hammer_radar_forward/tiny_live_fresh_cycle_checkpoint.ndjson 2>/dev/null || true

FINAL PHASE REPORT REQUIRED:
At the end, report:
- phase status
- files changed
- tests run
- smoke status
- safety status
- input_summary
- fresh_cycle_step_statuses
- fresh_cycle_blockers
- fresh_cycle_command_templates
- fresh_cycle_go_no_go_packet
- fresh_cycle_checkpoint_matrix
- fresh_cycle_checkpoint_overall_status
- exact files mutated
- recommended next operator move
- recommended next engineering move
- do not commit
- do not run real submit

Aggressive mode:
Complete in one pass.
Do not mutate env/config/lane controls.
Do not write external secret files.
Do not print secrets.
Do not persist secrets.
Do not sign.
Do not call Binance/network.
Do not submit.
Do not place orders.
Only record fresh-cycle checkpoint if exact confirmation command is explicitly run.
