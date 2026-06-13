You are in repo:
/home/josue/workspace/kernel/ai-agent-orchestrator-main

Follow:
- AGENTS.md
- codex_tasks/CODEX_RULES.md
- docs/hammer_radar/live_readiness/PHASE_INDEX.md

PHASE:
R256 Tiny-Live Operator Real Submit Runbook and Reconciliation

BRANCH:
r256-tiny-live-operator-real-submit-runbook-reconciliation

PHASE CLASSIFICATION:
Primary: OPERATOR RUNBOOK / RECONCILIATION SAFETY
Secondary: FINAL LIVE SUBMIT PROCEDURE, PARTIAL ORDER HANDLING, ABORT PATHS
Duplicate risk: EXTREME

WHY THIS PHASE EXISTS:
R255 Tiny-Live Actual Submit Gate has been committed.

R255 implemented the actual submit gate machinery, but correctly blocked live submit because:
- signed request timestamp was stale
- official lane was not currently tiny-live enabled
- live execution was not enabled

R255 proved:
- actual submit gate exists
- default preview does not submit
- dry preview records without submit
- rejected real submit does not execute
- order triplet is valid
- endpoint allowlist is valid
- runtime credentials are ready
- idempotency allows submit
- risk contract is valid
- no Binance order endpoint called
- no order placed
- no secrets leaked

R256 must create the human operator runbook and reconciliation workflow for the final manual real-submit event.

This phase must NOT submit.
This phase must NOT call Binance.
This phase must NOT call order endpoints.
This phase must NOT sign.
This phase must NOT regenerate signed requests.
This phase must NOT mutate live controls.

R256 is documentation + operator packet + local runbook ledger only.

OFFICIAL LANE:
BTCUSDT|8m|short|ladder_close_50_618

CURRENT KNOWN R255 BLOCKERS:
- signed_request_timestamp_stale
- official_lane_not_tiny_live
- live_execution_not_enabled

R256 must explicitly explain that before actual submit, operator must:
1. Run a fresh final readonly mark refresh.
2. Regenerate signed request if timestamp would be stale.
3. Confirm lane/tiny-live controls are intentionally armed.
4. Confirm kill-switch does not block.
5. Confirm no duplicate live submit exists.
6. Confirm exact triplet:
   - main SELL MARKET 0.007
   - stop BUY STOP_MARKET reduceOnly true
   - TP BUY TAKE_PROFIT_MARKET reduceOnly true
7. Run R255 dry preview immediately before real submit.
8. Only then consider running the exact R255 live submit command manually.

CORE INTENT:
Create:
1. Operator runbook markdown.
2. Machine-readable runbook/packet command.
3. Reconciliation checklist.
4. Partial success handling instructions.
5. Abort/cleanup decision tree.
6. R257 future phase placeholder for final pre-submit arming drill or manual live-submit checkpoint.

This phase should make the final manual step boring, explicit, and auditable.

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
- Build runbook markdown.
- Build runbook packet CLI.
- Append R256 runbook ledger under exact confirmation.
- Add tests.
- Add future R257 placeholder.

CONFIRMATION PHRASE:
I CONFIRM TINY LIVE OPERATOR RUNBOOK RECORDING ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL.

CAPABILITY SCAN FIRST:
Inspect:
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
- src/app/hammer_radar/operator/*submit* files
- src/app/hammer_radar/operator/*reconcile* files
- src/app/hammer_radar/operator/*actual* files
- src/app/hammer_radar/operator/*runbook* files if present
- src/app/hammer_radar/operator/*order* files
- src/app/hammer_radar/operator/*live* files
- src/app/hammer_radar/operator/*risk* files
- src/app/hammer_radar/operator/*kill* files

Inspect configs read-only:
- configs/hammer_radar/tiny_live_risk_contracts.json
- configs/hammer_radar/lane_controls.json
- configs/hammer_radar/*.json

Inspect ledgers/logs:
- logs/hammer_radar_forward/tiny_live_actual_submit_gate.ndjson
- logs/hammer_radar_forward/tiny_live_submit_gate_preview.ndjson
- logs/hammer_radar_forward/tiny_live_fresh_context_signed_request_regeneration_gate.ndjson
- logs/hammer_radar_forward/tiny_live_final_readonly_mark_price_refresh_gate.ndjson
- logs/hammer_radar_forward/tiny_live_submit_readiness_preview.ndjson
- logs/hammer_radar_forward/tiny_live_signed_request_write_gate.ndjson
- logs/hammer_radar_forward/tiny_live_executable_payload_write_gate.ndjson
- logs/hammer_radar_forward/tiny_live_stop_take_profit_source_gate.ndjson

Inspect docs:
- docs/hammer_radar/live_readiness/R255_TINY_LIVE_ACTUAL_SUBMIT_GATE.md
- docs/hammer_radar/live_readiness/R254_TINY_LIVE_SUBMIT_GATE_PREVIEW.md
- docs/hammer_radar/live_readiness/R253B_TINY_LIVE_FRESH_CONTEXT_SIGNED_REQUEST_REGENERATION_GATE.md
- docs/hammer_radar/live_readiness/R253_TINY_LIVE_FINAL_READONLY_MARK_PRICE_REFRESH_GATE.md
- docs/hammer_radar/live_readiness/R252_TINY_LIVE_SUBMIT_READINESS_PREVIEW.md
- docs/hammer_radar/live_readiness/PHASE_INDEX.md

Inspect tests:
- tests/hammer_radar/test_tiny_live_actual_submit_gate.py
- tests/hammer_radar/test_tiny_live_submit_gate_preview.py
- tests/hammer_radar/test_tiny_live_fresh_context_signed_request_regeneration_gate.py
- tests/hammer_radar/test_tiny_live_final_readonly_mark_price_refresh_gate.py
- tests/hammer_radar/test_tiny_live_submit_readiness_preview.py
- tests/hammer_radar/test_*reconcile* if present
- tests/hammer_radar/test_*runbook* if present
- tests/hammer_radar/test_*submit* if present

REUSE / EXTEND:
Reuse:
- R255 actual submit gate summaries.
- R254 submit gate preview summaries.
- Existing safety conventions.
- Existing NDJSON append helpers.

Do not implement live submit here.
Do not call Binance.
Do not sign.
Do not mutate controls.

REQUIRED MODULE:
Create:
src/app/hammer_radar/operator/tiny_live_operator_real_submit_runbook.py

Expose:
- build_tiny_live_operator_real_submit_runbook
- load_latest_tiny_live_actual_submit_gate
- load_latest_tiny_live_submit_gate_preview
- load_latest_tiny_live_fresh_context_signed_request_regeneration_gate
- summarize_current_submit_blockers_for_operator
- build_operator_pre_submit_checklist
- build_required_regeneration_sequence
- build_real_submit_command_template
- build_post_submit_reconciliation_checklist
- build_partial_success_handling_plan
- build_abort_cleanup_decision_tree
- build_duplicate_submit_protection_review
- build_operator_manual_decision_packet
- build_runbook_gate_matrix
- classify_tiny_live_operator_real_submit_runbook_status
- append_tiny_live_operator_real_submit_runbook_record
- load_tiny_live_operator_real_submit_runbook_records
- summarize_tiny_live_operator_real_submit_runbook_records

CLI:
Wire into inspect.py as:
tiny-live-operator-real-submit-runbook

Args:
- --record-operator-real-submit-runbook
- --confirm-tiny-live-operator-runbook <phrase>

Preview:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-operator-real-submit-runbook

Record:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-operator-real-submit-runbook \
  --record-operator-real-submit-runbook \
  --confirm-tiny-live-operator-runbook "I CONFIRM TINY LIVE OPERATOR RUNBOOK RECORDING ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL."

Rejected:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-operator-real-submit-runbook \
  --record-operator-real-submit-runbook \
  --confirm-tiny-live-operator-runbook "wrong"

STATUS ENUM:
- TINY_LIVE_OPERATOR_REAL_SUBMIT_RUNBOOK_READY
- TINY_LIVE_OPERATOR_REAL_SUBMIT_RUNBOOK_RECORDED
- TINY_LIVE_OPERATOR_REAL_SUBMIT_RUNBOOK_REJECTED
- TINY_LIVE_OPERATOR_REAL_SUBMIT_RUNBOOK_BLOCKED
- TINY_LIVE_OPERATOR_REAL_SUBMIT_RUNBOOK_ERROR

OVERALL STATUS ENUM:
- TINY_LIVE_OPERATOR_RUNBOOK_READY_FOR_RECORDING
- TINY_LIVE_OPERATOR_RUNBOOK_RECORDED_MANUAL_DECISION_REQUIRED
- TINY_LIVE_OPERATOR_RUNBOOK_REJECTED_BAD_CONFIRMATION
- TINY_LIVE_OPERATOR_RUNBOOK_BLOCKED_BY_MISSING_R255
- UNKNOWN_NEEDS_MANUAL_REVIEW

OUTPUT MUST INCLUDE:
{
  "status": "...",
  "generated_at": "...",
  "record_operator_real_submit_runbook_requested": false,
  "confirmation_valid": false,
  "operator_runbook_recorded": false,
  "target_scope": {
    "official_lane_key": "BTCUSDT|8m|short|ladder_close_50_618",
    "symbol": "BTCUSDT",
    "timeframe": "8m",
    "direction": "short",
    "operator_runbook_only": true,
    "submit_allowed": false,
    "order_placed": false,
    "binance_order_endpoint_called": false,
    "network_allowed": false
  },
  "input_summary": {
    "r255_actual_submit_gate_found": true/false,
    "r255_actual_submit_gate_valid": true/false,
    "r254_submit_gate_preview_found": true/false,
    "r253b_fresh_regeneration_found": true/false
  },
  "current_submit_blockers": {
    "blocked_by": [],
    "requires_regeneration": true/false,
    "requires_live_controls_arming": true/false,
    "requires_operator_manual_decision": true,
    "submit_allowed_now": false
  },
  "operator_pre_submit_checklist": [
    "... checklist item ..."
  ],
  "required_regeneration_sequence": {
    "required_if_timestamp_stale": true,
    "steps": [
      "run R253 final readonly refresh",
      "run R253B fresh context signed request regeneration",
      "run R254 submit gate preview",
      "run R255 actual submit gate dry preview"
    ]
  },
  "real_submit_command_template": {
    "command_is_template_only": true,
    "must_not_auto_run": true,
    "requires_manual_operator_paste": true,
    "command": "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect ...",
    "confirmation_phrase": "I CONFIRM TINY LIVE BTCUSDT 8M SHORT SUBMIT ONLY; PLACE EXACTLY THREE BINANCE FUTURES ORDERS FROM LATEST R253B SIGNED REQUEST; MAIN SELL MARKET 0.007 BTC; STOP BUY STOP_MARKET REDUCE_ONLY; TAKE_PROFIT BUY TAKE_PROFIT_MARKET REDUCE_ONLY; NO OTHER ORDERS."
  },
  "post_submit_reconciliation_checklist": [
    "record exchange order ids",
    "verify main order status",
    "verify stop reduceOnly order status",
    "verify take-profit reduceOnly order status",
    "verify no extra orders",
    "verify live execution ledger append",
    "verify idempotency key recorded"
  ],
  "partial_success_handling_plan": {
    "if_main_fails": [],
    "if_main_succeeds_stop_fails": [],
    "if_main_succeeds_tp_fails": [],
    "if_exit_order_duplicate": [],
    "if_unknown_exchange_response": []
  },
  "abort_cleanup_decision_tree": {
    "before_submit": [],
    "after_partial_submit": [],
    "after_full_submit": [],
    "if_reconciliation_fails": []
  },
  "duplicate_submit_protection_review": {
    "idempotency_key_required": true,
    "prior_live_submit_must_be_false": true,
    "do_not_retry_without_reconciliation": true
  },
  "operator_manual_decision_packet": {
    "operator_should_submit_now": false,
    "operator_should_regenerate_first": true/false,
    "operator_should_arm_live_controls_manually": true/false,
    "operator_should_review_reconciliation_plan": true,
    "next_required_human_action": "REVIEW_RUNBOOK|REGENERATE_SIGNED_REQUEST|ARM_LIVE_CONTROLS_MANUALLY|MANUAL_SUBMIT_DECISION|WAIT"
  },
  "runbook_gate_matrix": {
    "r255_available": true/false,
    "runbook_complete": true/false,
    "record_confirmed": true/false,
    "recorded": true/false,
    "submit_allowed": false,
    "order_placed": false,
    "blocked_by": []
  },
  "operator_runbook_overall_status": "...",
  "recommended_next_operator_move": "...",
  "recommended_next_engineering_move": "...",
  "do_not_run_yet": [
    "unreviewed live submit",
    "duplicate live submit",
    "manual submit without regeneration if timestamp stale",
    "manual submit without live controls arming review",
    "manual submit without reconciliation plan"
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
- operator_runbook_only=true
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
- secrets_read=false
- secrets_shown=false
- secrets_persisted=false
- secret_values_in_output=false
- global_live_flags_changed=false
- paper_live_separation_intact=true
- official_tiny_live_lane_changed=false

LEDGER:
logs/hammer_radar_forward/tiny_live_operator_real_submit_runbook.ndjson

Only append under exact confirmation phrase.

DOCS:
Create:
docs/hammer_radar/live_readiness/R256_TINY_LIVE_OPERATOR_REAL_SUBMIT_RUNBOOK_AND_RECONCILIATION.md

Create or update:
docs/hammer_radar/live_readiness/TINY_LIVE_REAL_SUBMIT_OPERATOR_RUNBOOK.md

Update:
docs/hammer_radar/live_readiness/PHASE_INDEX.md

FUTURE TASK:
Create:
codex_tasks/phases/R257_TINY_LIVE_FINAL_PRE_SUBMIT_ARMING_DRILL.md

R257 should:
- be the final pre-submit arming drill
- still no real submit
- verify operator has reviewed R256
- verify live controls intended state
- verify regeneration freshness
- verify exact R255 command is known
- produce a final “manual decision packet”
- never auto-run real submit

TESTS:
Create:
tests/hammer_radar/test_tiny_live_operator_real_submit_runbook.py

Tests must cover:
- CLI exists and returns JSON
- preview writes no ledger
- wrong confirmation rejects
- exact confirmation records runbook only
- no Binance/network calls
- no signing
- no submit
- no order
- command template includes --execute-actual-submit and --allow-real-binance-order-endpoint
- command template includes real R255 confirmation phrase
- checklist includes regeneration if timestamp stale
- checklist includes live controls arming review
- checklist includes idempotency/dedupe
- checklist includes post-submit reconciliation
- partial success plan covers main succeeds / stop fails
- partial success plan covers unknown exchange response
- abort tree exists
- no env/config/lane_controls mutation
- no secrets in output

VALIDATION:
Run py_compile:
- src/app/hammer_radar/operator/tiny_live_operator_real_submit_runbook.py
- src/app/hammer_radar/operator/inspect.py

Run focused test:
- tests/hammer_radar/test_tiny_live_operator_real_submit_runbook.py

Run related tests:
- tests/hammer_radar/test_tiny_live_actual_submit_gate.py
- tests/hammer_radar/test_tiny_live_submit_gate_preview.py
- tests/hammer_radar/test_tiny_live_fresh_context_signed_request_regeneration_gate.py

Run full:
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar

SMOKE:
Preview:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-operator-real-submit-runbook \
  | jq '.status, .target_scope, .input_summary, .current_submit_blockers, .operator_pre_submit_checklist, .required_regeneration_sequence, .real_submit_command_template, .post_submit_reconciliation_checklist, .partial_success_handling_plan, .abort_cleanup_decision_tree, .duplicate_submit_protection_review, .operator_manual_decision_packet, .runbook_gate_matrix, .operator_runbook_overall_status, .recommended_next_operator_move, .recommended_next_engineering_move, .do_not_run_yet, .safety'

Record:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-operator-real-submit-runbook \
  --record-operator-real-submit-runbook \
  --confirm-tiny-live-operator-runbook "I CONFIRM TINY LIVE OPERATOR RUNBOOK RECORDING ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL." \
  | jq '.status, .operator_runbook_recorded, .runbook_gate_matrix, .operator_manual_decision_packet, .operator_runbook_overall_status, .safety'

Rejected:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-operator-real-submit-runbook \
  --record-operator-real-submit-runbook \
  --confirm-tiny-live-operator-runbook "wrong" \
  | jq '.status, .confirmation_valid, .operator_runbook_recorded, .safety'

Secret leak check:
PYTHONPATH=. .venv/bin/python - <<'PY'
import os
from pathlib import Path

path = Path("logs/hammer_radar_forward/tiny_live_operator_real_submit_runbook.ndjson")
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
git status --short logs/hammer_radar_forward/tiny_live_operator_real_submit_runbook.ndjson || true
tail -n 3 logs/hammer_radar_forward/tiny_live_operator_real_submit_runbook.ndjson 2>/dev/null || true

FINAL PHASE REPORT REQUIRED:
At the end, report:
- phase status
- files changed
- tests run
- smoke status
- safety status
- current_submit_blockers
- operator_pre_submit_checklist
- required_regeneration_sequence
- real_submit_command_template
- post_submit_reconciliation_checklist
- partial_success_handling_plan
- abort_cleanup_decision_tree
- duplicate_submit_protection_review
- operator_manual_decision_packet
- runbook_gate_matrix
- operator_runbook_overall_status
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
Only record operator runbook if exact confirmation command is explicitly run.
