You are in repo:
/home/josue/workspace/kernel/ai-agent-orchestrator-main

Follow:
- AGENTS.md
- codex_tasks/CODEX_RULES.md
- docs/hammer_radar/live_readiness/PHASE_INDEX.md
- docs/hammer_radar/live_readiness/TINY_LIVE_REAL_SUBMIT_OPERATOR_RUNBOOK.md

PHASE:
R258 Tiny-Live Manual Submit Checkpoint

BRANCH:
r258-tiny-live-manual-submit-checkpoint

PHASE CLASSIFICATION:
Primary: FINAL MANUAL CHECKPOINT / GO-NO-GO PACKET
Secondary: PRE-LIVE DECISION SAFETY, BLOCKER CONSOLIDATION, REGENERATION PATH ORCHESTRATION
Duplicate risk: EXTREME

WHY THIS PHASE EXISTS:
R257 Tiny-Live Final Pre-Submit Arming Drill has been committed.

R257 confirmed:
- R256 runbook is available
- R255 actual submit gate exists
- R254 submit gate preview exists
- R253B fresh regeneration exists
- exact submit command template exists
- reconciliation plan exists
- final manual decision is required
- submit is still forbidden
- order is still not placed

R257 preserved current blockers:
- signed_request_timestamp_stale
- official_lane_not_tiny_live
- live_execution_not_enabled

R258 must create the final manual submit checkpoint packet. It must not submit, not arm live controls, not regenerate, not sign, and not call Binance.

R258 should tell the operator, in one command output:
1. whether the system is currently blocked
2. why it is blocked
3. whether a fresh regeneration cycle is required
4. whether live controls are still off
5. whether the R255 final command exists
6. what exact sequence must happen next
7. what must absolutely not be done
8. whether the system is ready for a later R259 fresh-cycle checkpoint

This is a manual checkpoint only.
This is not submit.
This is not signing.
This is not live-control arming.
This is not Binance.

OFFICIAL LANE:
BTCUSDT|8m|short|ladder_close_50_618

CURRENT KNOWN BLOCKERS:
- signed_request_timestamp_stale
- official_lane_not_tiny_live
- live_execution_not_enabled

EXPECTED SAFE R258 RESULT:
- submit_allowed=false
- order_placed=false
- binance_order_endpoint_called=false
- network_allowed=false
- live_controls_armed_by_phase=false
- operator_should_submit_now=false
- operator_should_regenerate_first=true if timestamp stale
- operator_should_arm_live_controls_manually=true if controls still off
- operator_should_run_fresh_cycle_next=true
- operator_manual_decision_required=true

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
- Build manual checkpoint packet.
- Append R258 checkpoint ledger only under exact confirmation.
- Add docs/tests.
- Create R259 future task.

CONFIRMATION PHRASE:
I CONFIRM TINY LIVE MANUAL SUBMIT CHECKPOINT RECORDING ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL.

CAPABILITY SCAN FIRST:
Inspect:
- src/app/hammer_radar/operator/tiny_live_final_pre_submit_arming_drill.py
- src/app/hammer_radar/operator/tiny_live_operator_real_submit_runbook.py
- src/app/hammer_radar/operator/tiny_live_actual_submit_gate.py
- src/app/hammer_radar/operator/tiny_live_submit_gate_preview.py
- src/app/hammer_radar/operator/tiny_live_fresh_context_signed_request_regeneration_gate.py
- src/app/hammer_radar/operator/tiny_live_final_readonly_mark_price_refresh_gate.py
- src/app/hammer_radar/operator/tiny_live_submit_readiness_preview.py
- src/app/hammer_radar/operator/inspect.py
- src/app/hammer_radar/operator/*submit* files
- src/app/hammer_radar/operator/*checkpoint* files if present
- src/app/hammer_radar/operator/*arming* files
- src/app/hammer_radar/operator/*runbook* files
- src/app/hammer_radar/operator/*reconcile* files
- src/app/hammer_radar/operator/*live* files
- src/app/hammer_radar/operator/*lane* files
- src/app/hammer_radar/operator/*risk* files
- src/app/hammer_radar/operator/*kill* files
- src/app/hammer_radar/operator/*signed* files

Inspect configs read-only:
- configs/hammer_radar/tiny_live_risk_contracts.json
- configs/hammer_radar/lane_controls.json
- configs/hammer_radar/*.json

Inspect ledgers/logs:
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
- docs/hammer_radar/live_readiness/R257_TINY_LIVE_FINAL_PRE_SUBMIT_ARMING_DRILL.md
- docs/hammer_radar/live_readiness/R256_TINY_LIVE_OPERATOR_REAL_SUBMIT_RUNBOOK_AND_RECONCILIATION.md
- docs/hammer_radar/live_readiness/TINY_LIVE_REAL_SUBMIT_OPERATOR_RUNBOOK.md
- docs/hammer_radar/live_readiness/R255_TINY_LIVE_ACTUAL_SUBMIT_GATE.md
- docs/hammer_radar/live_readiness/R254_TINY_LIVE_SUBMIT_GATE_PREVIEW.md
- docs/hammer_radar/live_readiness/R253B_TINY_LIVE_FRESH_CONTEXT_SIGNED_REQUEST_REGENERATION_GATE.md
- docs/hammer_radar/live_readiness/PHASE_INDEX.md

Inspect tests:
- tests/hammer_radar/test_tiny_live_final_pre_submit_arming_drill.py
- tests/hammer_radar/test_tiny_live_operator_real_submit_runbook.py
- tests/hammer_radar/test_tiny_live_actual_submit_gate.py
- tests/hammer_radar/test_tiny_live_submit_gate_preview.py
- tests/hammer_radar/test_tiny_live_fresh_context_signed_request_regeneration_gate.py
- tests/hammer_radar/test_*checkpoint* if present
- tests/hammer_radar/test_*arming* if present
- tests/hammer_radar/test_*submit* if present
- tests/hammer_radar/test_*live* if present

REUSE / EXTEND:
Reuse:
- R257 final arming drill loaders and summaries.
- R256 operator runbook loaders.
- R255 actual submit gate blocker summaries.
- R254 submit gate preview summaries.
- Existing safety conventions.
- Existing NDJSON append helpers.

Do not implement live submit here.
Do not call Binance.
Do not sign.
Do not mutate controls.
Do not arm live controls.
Do not regenerate signed requests.

REQUIRED MODULE:
Create:
src/app/hammer_radar/operator/tiny_live_manual_submit_checkpoint.py

Expose:
- build_tiny_live_manual_submit_checkpoint
- load_latest_tiny_live_final_pre_submit_arming_drill
- load_latest_tiny_live_operator_real_submit_runbook
- load_latest_tiny_live_actual_submit_gate
- load_latest_tiny_live_submit_gate_preview
- load_latest_tiny_live_fresh_context_signed_request_regeneration_gate
- summarize_checkpoint_inputs
- summarize_current_manual_submit_blockers
- summarize_fresh_cycle_requirement
- summarize_live_controls_checkpoint
- summarize_real_submit_command_checkpoint
- summarize_reconciliation_checkpoint
- build_manual_submit_go_no_go_packet
- build_manual_submit_checkpoint_matrix
- classify_tiny_live_manual_submit_checkpoint_status
- append_tiny_live_manual_submit_checkpoint_record
- load_tiny_live_manual_submit_checkpoint_records
- summarize_tiny_live_manual_submit_checkpoint_records

CLI:
Wire into inspect.py as:
tiny-live-manual-submit-checkpoint

Args:
- --record-manual-submit-checkpoint
- --confirm-tiny-live-manual-submit-checkpoint <phrase>

Preview:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-manual-submit-checkpoint

Record:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-manual-submit-checkpoint \
  --record-manual-submit-checkpoint \
  --confirm-tiny-live-manual-submit-checkpoint "I CONFIRM TINY LIVE MANUAL SUBMIT CHECKPOINT RECORDING ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL."

Rejected:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-manual-submit-checkpoint \
  --record-manual-submit-checkpoint \
  --confirm-tiny-live-manual-submit-checkpoint "wrong"

STATUS ENUM:
- TINY_LIVE_MANUAL_SUBMIT_CHECKPOINT_READY
- TINY_LIVE_MANUAL_SUBMIT_CHECKPOINT_RECORDED
- TINY_LIVE_MANUAL_SUBMIT_CHECKPOINT_REJECTED
- TINY_LIVE_MANUAL_SUBMIT_CHECKPOINT_BLOCKED
- TINY_LIVE_MANUAL_SUBMIT_CHECKPOINT_ERROR

OVERALL STATUS ENUM:
- TINY_LIVE_MANUAL_CHECKPOINT_READY_FOR_RECORDING
- TINY_LIVE_MANUAL_CHECKPOINT_RECORDED_FRESH_CYCLE_REQUIRED
- TINY_LIVE_MANUAL_CHECKPOINT_RECORDED_MANUAL_DECISION_REQUIRED
- TINY_LIVE_MANUAL_CHECKPOINT_REJECTED_BAD_CONFIRMATION
- TINY_LIVE_MANUAL_CHECKPOINT_BLOCKED_BY_MISSING_R257
- UNKNOWN_NEEDS_MANUAL_REVIEW

OUTPUT MUST INCLUDE:
{
  "status": "...",
  "generated_at": "...",
  "record_manual_submit_checkpoint_requested": false,
  "confirmation_valid": false,
  "manual_submit_checkpoint_recorded": false,
  "target_scope": {
    "official_lane_key": "BTCUSDT|8m|short|ladder_close_50_618",
    "symbol": "BTCUSDT",
    "timeframe": "8m",
    "direction": "short",
    "manual_submit_checkpoint_only": true,
    "submit_allowed": false,
    "order_placed": false,
    "binance_order_endpoint_called": false,
    "network_allowed": false
  },
  "input_summary": {
    "r257_final_arming_drill_found": true/false,
    "r257_final_arming_drill_valid": true/false,
    "r256_operator_runbook_found": true/false,
    "r255_actual_submit_gate_found": true/false,
    "r254_submit_gate_preview_found": true/false,
    "r253b_fresh_regeneration_found": true/false
  },
  "manual_submit_blocker_summary": {
    "blocked_by": [],
    "submit_allowed_now": false,
    "operator_should_not_submit_now": true,
    "fresh_cycle_required": true/false,
    "live_controls_manual_review_required": true/false,
    "manual_decision_required": true
  },
  "fresh_cycle_requirement": {
    "required_now": true/false,
    "reason": "timestamp_stale|controls_blocked|manual_checkpoint|unknown",
    "sequence": [
      "R253 final readonly refresh",
      "R253B fresh signed request regeneration",
      "R254 submit gate preview",
      "R255 dry preview",
      "R258 manual checkpoint re-check"
    ],
    "r259_future_phase": "R259_TINY_LIVE_FRESH_CYCLE_CHECKPOINT"
  },
  "live_controls_checkpoint": {
    "live_execution_enabled": true/false,
    "official_lane_allowed": true/false,
    "kill_switch_allows_tiny_live": true/false,
    "manual_arming_required": true/false,
    "auto_armed_by_this_phase": false
  },
  "real_submit_command_checkpoint": {
    "template_available": true/false,
    "must_not_auto_run": true,
    "requires_manual_operator_paste": true,
    "contains_execute_flag": true/false,
    "contains_allow_real_endpoint_flag": true/false,
    "contains_exact_confirmation_phrase": true/false
  },
  "reconciliation_checkpoint": {
    "post_submit_reconciliation_ready": true/false,
    "partial_success_plan_ready": true/false,
    "abort_cleanup_ready": true/false,
    "duplicate_submit_protection_ready": true/false
  },
  "manual_submit_go_no_go_packet": {
    "go_for_manual_submit_now": false,
    "no_go_reasons": [],
    "operator_should_regenerate_first": true/false,
    "operator_should_arm_live_controls_manually": true/false,
    "operator_should_run_r255_dry_preview": true,
    "operator_should_review_reconciliation": true,
    "operator_should_submit_now": false,
    "next_required_human_action": "RUN_FRESH_CYCLE|ARM_LIVE_CONTROLS_MANUALLY|RUN_R255_DRY_PREVIEW|MANUAL_DECISION_REQUIRED|WAIT|FIX_BLOCKER"
  },
  "manual_submit_checkpoint_matrix": {
    "r257_available": true/false,
    "fresh_cycle_requirement_known": true/false,
    "live_controls_state_known": true/false,
    "submit_command_known": true/false,
    "reconciliation_ready": true/false,
    "record_confirmed": true/false,
    "recorded": true/false,
    "submit_allowed": false,
    "order_placed": false,
    "blocked_by": []
  },
  "manual_submit_checkpoint_overall_status": "...",
  "recommended_next_operator_move": "...",
  "recommended_next_engineering_move": "...",
  "do_not_run_yet": [
    "real submit without fresh cycle",
    "real submit without manual live-control arming review",
    "real submit without R255 dry preview",
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
- manual_submit_checkpoint_only=true
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
logs/hammer_radar_forward/tiny_live_manual_submit_checkpoint.ndjson

Only append under exact confirmation phrase.

DOCS:
Create:
docs/hammer_radar/live_readiness/R258_TINY_LIVE_MANUAL_SUBMIT_CHECKPOINT.md

Update:
docs/hammer_radar/live_readiness/TINY_LIVE_REAL_SUBMIT_OPERATOR_RUNBOOK.md

Update:
docs/hammer_radar/live_readiness/PHASE_INDEX.md

FUTURE TASK:
Create:
codex_tasks/phases/R259_TINY_LIVE_FRESH_CYCLE_CHECKPOINT.md

R259 should:
- still no real submit
- perform/coordinate the fresh-cycle checkpoint:
  - R253 readonly refresh
  - R253B regeneration
  - R254 preview
  - R255 dry preview
- verify outputs are fresh enough
- verify live controls intended state
- produce final R260 manual live-submit execution checkpoint
- never auto-submit

TESTS:
Create:
tests/hammer_radar/test_tiny_live_manual_submit_checkpoint.py

Tests must cover:
- CLI exists and returns JSON
- preview writes no ledger
- wrong confirmation rejects
- exact confirmation records checkpoint only
- no Binance/network calls
- no signing
- no submit
- no order
- summarizes R257 blockers
- detects fresh cycle required when timestamp stale
- detects live controls manual review required
- detects real submit command readiness
- detects reconciliation readiness
- go_for_manual_submit_now=false while blockers remain
- no env/config/lane_controls mutation
- no secrets in output

VALIDATION:
Run py_compile:
- src/app/hammer_radar/operator/tiny_live_manual_submit_checkpoint.py
- src/app/hammer_radar/operator/inspect.py

Run focused test:
- tests/hammer_radar/test_tiny_live_manual_submit_checkpoint.py

Run related tests:
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
  tiny-live-manual-submit-checkpoint \
  | jq '.status, .target_scope, .input_summary, .manual_submit_blocker_summary, .fresh_cycle_requirement, .live_controls_checkpoint, .real_submit_command_checkpoint, .reconciliation_checkpoint, .manual_submit_go_no_go_packet, .manual_submit_checkpoint_matrix, .manual_submit_checkpoint_overall_status, .recommended_next_operator_move, .recommended_next_engineering_move, .do_not_run_yet, .safety'

Record:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-manual-submit-checkpoint \
  --record-manual-submit-checkpoint \
  --confirm-tiny-live-manual-submit-checkpoint "I CONFIRM TINY LIVE MANUAL SUBMIT CHECKPOINT RECORDING ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL." \
  | jq '.status, .manual_submit_checkpoint_recorded, .manual_submit_go_no_go_packet, .manual_submit_checkpoint_matrix, .manual_submit_checkpoint_overall_status, .safety'

Rejected:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-manual-submit-checkpoint \
  --record-manual-submit-checkpoint \
  --confirm-tiny-live-manual-submit-checkpoint "wrong" \
  | jq '.status, .confirmation_valid, .manual_submit_checkpoint_recorded, .safety'

Secret leak check:
PYTHONPATH=. .venv/bin/python - <<'PY'
import os
from pathlib import Path

path = Path("logs/hammer_radar_forward/tiny_live_manual_submit_checkpoint.ndjson")
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
git status --short logs/hammer_radar_forward/tiny_live_manual_submit_checkpoint.ndjson || true
tail -n 3 logs/hammer_radar_forward/tiny_live_manual_submit_checkpoint.ndjson 2>/dev/null || true

FINAL PHASE REPORT REQUIRED:
At the end, report:
- phase status
- files changed
- tests run
- smoke status
- safety status
- manual_submit_blocker_summary
- fresh_cycle_requirement
- live_controls_checkpoint
- real_submit_command_checkpoint
- reconciliation_checkpoint
- manual_submit_go_no_go_packet
- manual_submit_checkpoint_matrix
- manual_submit_checkpoint_overall_status
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
Only record manual submit checkpoint if exact confirmation command is explicitly run.
