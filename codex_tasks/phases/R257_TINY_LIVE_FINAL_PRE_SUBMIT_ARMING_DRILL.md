You are in repo:
/home/josue/workspace/kernel/ai-agent-orchestrator-main

Follow:
- AGENTS.md
- codex_tasks/CODEX_RULES.md
- docs/hammer_radar/live_readiness/PHASE_INDEX.md

PHASE:
R257 Tiny-Live Final Pre-Submit Arming Drill

BRANCH:
r257-tiny-live-final-pre-submit-arming-drill

PHASE CLASSIFICATION:
Primary: FINAL PRE-SUBMIT ARMING DRILL
Secondary: OPERATOR DECISION PACKET, LIVE CONTROL REVIEW, REGENERATION REQUIREMENT REVIEW
Duplicate risk: EXTREME

WHY THIS PHASE EXISTS:
R256 Tiny-Live Operator Real Submit Runbook and Reconciliation has been committed.

R256 created the operator real-submit runbook and confirmed current blockers:
- signed_request_timestamp_stale
- official_lane_not_tiny_live
- live_execution_not_enabled

R256 documented:
- regeneration sequence
- manual real-submit command template
- partial success handling
- abort cleanup decision tree
- duplicate submit protection
- post-submit reconciliation checklist

R257 must create the final pre-submit arming drill.

This phase must NOT submit.
This phase must NOT call Binance.
This phase must NOT call order endpoints.
This phase must NOT sign.
This phase must NOT regenerate signed requests.
This phase must NOT mutate live controls.
This phase must NOT arm live controls automatically.

R257 exists to produce a final manual decision packet that tells the operator exactly what remains before any real submit can be manually considered.

CORE INTENT:
Create a final pre-submit arming drill that:
1. Reads latest R256 operator runbook.
2. Reads latest R255 actual submit gate dry preview.
3. Reads latest R254 submit gate preview.
4. Reads latest R253B fresh regeneration artifact.
5. Reads lane controls and tiny-live risk contract read-only.
6. Summarizes current blockers.
7. Confirms whether signed request regeneration is required.
8. Confirms live execution/tiny-live lane controls are currently blocking or intentionally armed.
9. Confirms exact real-submit command template exists but must not be run automatically.
10. Confirms reconciliation/abort/partial-success plans exist.
11. Produces a final manual decision packet.
12. Produces future R258 manual-submit checkpoint placeholder.

This is a final drill only.
This is not submit.
This is not arming.
This is not signing.
This is not order placement.

OFFICIAL LANE:
BTCUSDT|8m|short|ladder_close_50_618

KNOWN CURRENT BLOCKERS FROM R256:
- signed_request_timestamp_stale
- official_lane_not_tiny_live
- live_execution_not_enabled

EXPECTED SAFE R257 RESULT:
- submit_allowed=false
- order_placed=false
- binance_order_endpoint_called=false
- network_allowed=false
- operator_should_submit_now=false
- operator_should_regenerate_first=true if timestamp stale
- operator_should_arm_live_controls_manually=true if live controls still off
- operator_should_review_reconciliation_plan=true
- final_manual_decision_required=true

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
- No sudo.
- Do not commit.
- Do not merge.
- Do not tag.
- Do not touch or stage AGENTS.md.

ALLOWED:
- Read local ledgers/configs.
- Build final arming drill packet.
- Append R257 arming drill ledger under exact confirmation.
- Add docs/tests.
- Create R258 future task.

CONFIRMATION PHRASE:
I CONFIRM TINY LIVE FINAL PRE-SUBMIT ARMING DRILL RECORDING ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL.

CAPABILITY SCAN FIRST:
Inspect:
- src/app/hammer_radar/operator/tiny_live_operator_real_submit_runbook.py
- src/app/hammer_radar/operator/tiny_live_actual_submit_gate.py
- src/app/hammer_radar/operator/tiny_live_submit_gate_preview.py
- src/app/hammer_radar/operator/tiny_live_fresh_context_signed_request_regeneration_gate.py
- src/app/hammer_radar/operator/tiny_live_final_readonly_mark_price_refresh_gate.py
- src/app/hammer_radar/operator/tiny_live_submit_readiness_preview.py
- src/app/hammer_radar/operator/inspect.py
- src/app/hammer_radar/operator/*submit* files
- src/app/hammer_radar/operator/*runbook* files
- src/app/hammer_radar/operator/*arming* files if present
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
- docs/hammer_radar/live_readiness/R256_TINY_LIVE_OPERATOR_REAL_SUBMIT_RUNBOOK_AND_RECONCILIATION.md
- docs/hammer_radar/live_readiness/TINY_LIVE_REAL_SUBMIT_OPERATOR_RUNBOOK.md
- docs/hammer_radar/live_readiness/R255_TINY_LIVE_ACTUAL_SUBMIT_GATE.md
- docs/hammer_radar/live_readiness/R254_TINY_LIVE_SUBMIT_GATE_PREVIEW.md
- docs/hammer_radar/live_readiness/R253B_TINY_LIVE_FRESH_CONTEXT_SIGNED_REQUEST_REGENERATION_GATE.md
- docs/hammer_radar/live_readiness/PHASE_INDEX.md

Inspect tests:
- tests/hammer_radar/test_tiny_live_operator_real_submit_runbook.py
- tests/hammer_radar/test_tiny_live_actual_submit_gate.py
- tests/hammer_radar/test_tiny_live_submit_gate_preview.py
- tests/hammer_radar/test_tiny_live_fresh_context_signed_request_regeneration_gate.py
- tests/hammer_radar/test_*arming* if present
- tests/hammer_radar/test_*runbook* if present
- tests/hammer_radar/test_*submit* if present
- tests/hammer_radar/test_*live* if present

REUSE / EXTEND:
Reuse:
- R256 runbook loader/summaries.
- R255 blocker summaries.
- R254 submit gate preview summaries.
- Existing safety conventions.
- Existing NDJSON append helpers.

Do not implement submit here.
Do not call Binance.
Do not sign.
Do not mutate controls.
Do not arm live controls.

REQUIRED MODULE:
Create:
src/app/hammer_radar/operator/tiny_live_final_pre_submit_arming_drill.py

Expose:
- build_tiny_live_final_pre_submit_arming_drill
- load_latest_tiny_live_operator_real_submit_runbook
- load_latest_tiny_live_actual_submit_gate
- load_latest_tiny_live_submit_gate_preview
- load_latest_tiny_live_fresh_context_signed_request_regeneration_gate
- summarize_pre_submit_blockers
- summarize_signed_request_regeneration_requirement
- summarize_live_control_intent_state
- summarize_exact_submit_command_readiness
- summarize_reconciliation_readiness
- build_final_manual_decision_packet
- build_final_pre_submit_arming_drill_matrix
- classify_tiny_live_final_pre_submit_arming_drill_status
- append_tiny_live_final_pre_submit_arming_drill_record
- load_tiny_live_final_pre_submit_arming_drill_records
- summarize_tiny_live_final_pre_submit_arming_drill_records

CLI:
Wire into inspect.py as:
tiny-live-final-pre-submit-arming-drill

Args:
- --record-final-pre-submit-arming-drill
- --confirm-tiny-live-final-pre-submit-arming-drill <phrase>

Preview:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-final-pre-submit-arming-drill

Record:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-final-pre-submit-arming-drill \
  --record-final-pre-submit-arming-drill \
  --confirm-tiny-live-final-pre-submit-arming-drill "I CONFIRM TINY LIVE FINAL PRE-SUBMIT ARMING DRILL RECORDING ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL."

Rejected:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-final-pre-submit-arming-drill \
  --record-final-pre-submit-arming-drill \
  --confirm-tiny-live-final-pre-submit-arming-drill "wrong"

STATUS ENUM:
- TINY_LIVE_FINAL_PRE_SUBMIT_ARMING_DRILL_READY
- TINY_LIVE_FINAL_PRE_SUBMIT_ARMING_DRILL_RECORDED
- TINY_LIVE_FINAL_PRE_SUBMIT_ARMING_DRILL_REJECTED
- TINY_LIVE_FINAL_PRE_SUBMIT_ARMING_DRILL_BLOCKED
- TINY_LIVE_FINAL_PRE_SUBMIT_ARMING_DRILL_ERROR

OVERALL STATUS ENUM:
- TINY_LIVE_FINAL_ARMING_DRILL_READY_FOR_RECORDING
- TINY_LIVE_FINAL_ARMING_DRILL_RECORDED_MANUAL_DECISION_REQUIRED
- TINY_LIVE_FINAL_ARMING_DRILL_REJECTED_BAD_CONFIRMATION
- TINY_LIVE_FINAL_ARMING_DRILL_BLOCKED_BY_MISSING_R256
- UNKNOWN_NEEDS_MANUAL_REVIEW

OUTPUT MUST INCLUDE:
{
  "status": "...",
  "generated_at": "...",
  "record_final_pre_submit_arming_drill_requested": false,
  "confirmation_valid": false,
  "final_pre_submit_arming_drill_recorded": false,
  "target_scope": {
    "official_lane_key": "BTCUSDT|8m|short|ladder_close_50_618",
    "symbol": "BTCUSDT",
    "timeframe": "8m",
    "direction": "short",
    "final_pre_submit_arming_drill_only": true,
    "submit_allowed": false,
    "order_placed": false,
    "binance_order_endpoint_called": false,
    "network_allowed": false
  },
  "input_summary": {
    "r256_operator_runbook_found": true/false,
    "r256_operator_runbook_valid": true/false,
    "r255_actual_submit_gate_found": true/false,
    "r254_submit_gate_preview_found": true/false,
    "r253b_fresh_regeneration_found": true/false
  },
  "pre_submit_blocker_summary": {
    "blocked_by": [],
    "submit_allowed_now": false,
    "requires_regeneration": true/false,
    "requires_live_controls_arming_review": true/false,
    "requires_manual_operator_decision": true
  },
  "signed_request_regeneration_requirement": {
    "regeneration_required_now": true/false,
    "reason": "timestamp_stale|fresh_enough|unknown",
    "required_sequence": [
      "R253 final readonly refresh",
      "R253B fresh signed request regeneration",
      "R254 submit gate preview",
      "R255 dry preview"
    ]
  },
  "live_control_intent_state": {
    "live_execution_enabled": true/false,
    "official_lane_allowed": true/false,
    "kill_switch_allows_tiny_live": true/false,
    "operator_must_arm_manually": true/false,
    "auto_armed_by_this_phase": false
  },
  "exact_submit_command_readiness": {
    "template_available": true/false,
    "contains_execute_flag": true/false,
    "contains_allow_real_endpoint_flag": true/false,
    "contains_exact_confirmation_phrase": true/false,
    "must_not_auto_run": true
  },
  "reconciliation_readiness": {
    "post_submit_reconciliation_checklist_present": true/false,
    "partial_success_plan_present": true/false,
    "abort_cleanup_tree_present": true/false,
    "duplicate_submit_protection_present": true/false
  },
  "final_manual_decision_packet": {
    "operator_should_submit_now": false,
    "operator_should_regenerate_first": true/false,
    "operator_should_arm_live_controls_manually": true/false,
    "operator_should_run_r255_dry_preview_after_regeneration": true,
    "operator_should_review_runbook_again_before_manual_submit": true,
    "manual_submit_decision_required": true,
    "next_required_human_action": "REGENERATE_SIGNED_REQUEST|ARM_LIVE_CONTROLS_MANUALLY|RUN_R255_DRY_PREVIEW|MANUAL_SUBMIT_DECISION|WAIT|FIX_BLOCKER"
  },
  "final_pre_submit_arming_drill_matrix": {
    "r256_available": true/false,
    "runbook_reviewed": true/false,
    "regeneration_status_known": true/false,
    "live_control_intent_known": true/false,
    "exact_submit_command_known": true/false,
    "reconciliation_ready": true/false,
    "record_confirmed": true/false,
    "recorded": true/false,
    "submit_allowed": false,
    "order_placed": false,
    "blocked_by": []
  },
  "final_pre_submit_arming_drill_overall_status": "...",
  "recommended_next_operator_move": "...",
  "recommended_next_engineering_move": "...",
  "do_not_run_yet": [
    "real submit without fresh signed request",
    "real submit without explicit live controls arming",
    "real submit without R255 dry preview",
    "real submit without reconciliation plan",
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
- final_pre_submit_arming_drill_only=true
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
logs/hammer_radar_forward/tiny_live_final_pre_submit_arming_drill.ndjson

Only append under exact confirmation phrase.

DOCS:
Create:
docs/hammer_radar/live_readiness/R257_TINY_LIVE_FINAL_PRE_SUBMIT_ARMING_DRILL.md

Update:
docs/hammer_radar/live_readiness/TINY_LIVE_REAL_SUBMIT_OPERATOR_RUNBOOK.md

Update:
docs/hammer_radar/live_readiness/PHASE_INDEX.md

FUTURE TASK:
Create:
codex_tasks/phases/R258_TINY_LIVE_MANUAL_SUBMIT_CHECKPOINT.md

R258 should:
- still not auto-submit
- be the manual checkpoint phase immediately before any user-run real submit command
- verify regeneration is fresh within seconds
- verify live controls are intentionally armed by operator
- verify R255 dry preview is green
- present final yes/no manual command packet
- never execute real submit automatically

TESTS:
Create:
tests/hammer_radar/test_tiny_live_final_pre_submit_arming_drill.py

Tests must cover:
- CLI exists and returns JSON
- preview writes no ledger
- wrong confirmation rejects
- exact confirmation records drill only
- no Binance/network calls
- no signing
- no submit
- no order
- summarizes R256 blockers
- detects regeneration required when timestamp stale
- detects live controls require manual arming
- detects real submit command template exists
- detects reconciliation plan exists
- final decision packet says operator_should_submit_now=false
- no env/config/lane_controls mutation
- no secrets in output

VALIDATION:
Run py_compile:
- src/app/hammer_radar/operator/tiny_live_final_pre_submit_arming_drill.py
- src/app/hammer_radar/operator/inspect.py

Run focused test:
- tests/hammer_radar/test_tiny_live_final_pre_submit_arming_drill.py

Run related tests:
- tests/hammer_radar/test_tiny_live_operator_real_submit_runbook.py
- tests/hammer_radar/test_tiny_live_actual_submit_gate.py
- tests/hammer_radar/test_tiny_live_submit_gate_preview.py

Run full:
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar

SMOKE:
Preview:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-final-pre-submit-arming-drill \
  | jq '.status, .target_scope, .input_summary, .pre_submit_blocker_summary, .signed_request_regeneration_requirement, .live_control_intent_state, .exact_submit_command_readiness, .reconciliation_readiness, .final_manual_decision_packet, .final_pre_submit_arming_drill_matrix, .final_pre_submit_arming_drill_overall_status, .recommended_next_operator_move, .recommended_next_engineering_move, .do_not_run_yet, .safety'

Record:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-final-pre-submit-arming-drill \
  --record-final-pre-submit-arming-drill \
  --confirm-tiny-live-final-pre-submit-arming-drill "I CONFIRM TINY LIVE FINAL PRE-SUBMIT ARMING DRILL RECORDING ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL." \
  | jq '.status, .final_pre_submit_arming_drill_recorded, .final_manual_decision_packet, .final_pre_submit_arming_drill_matrix, .final_pre_submit_arming_drill_overall_status, .safety'

Rejected:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-final-pre-submit-arming-drill \
  --record-final-pre-submit-arming-drill \
  --confirm-tiny-live-final-pre-submit-arming-drill "wrong" \
  | jq '.status, .confirmation_valid, .final_pre_submit_arming_drill_recorded, .safety'

Secret leak check:
PYTHONPATH=. .venv/bin/python - <<'PY'
import os
from pathlib import Path

path = Path("logs/hammer_radar_forward/tiny_live_final_pre_submit_arming_drill.ndjson")
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
git status --short logs/hammer_radar_forward/tiny_live_final_pre_submit_arming_drill.ndjson || true
tail -n 3 logs/hammer_radar_forward/tiny_live_final_pre_submit_arming_drill.ndjson 2>/dev/null || true

FINAL PHASE REPORT REQUIRED:
At the end, report:
- phase status
- files changed
- tests run
- smoke status
- safety status
- pre_submit_blocker_summary
- signed_request_regeneration_requirement
- live_control_intent_state
- exact_submit_command_readiness
- reconciliation_readiness
- final_manual_decision_packet
- final_pre_submit_arming_drill_matrix
- final_pre_submit_arming_drill_overall_status
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
Only record final pre-submit arming drill if exact confirmation command is explicitly run.
