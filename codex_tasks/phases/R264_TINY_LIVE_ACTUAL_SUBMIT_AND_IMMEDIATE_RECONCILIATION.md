You are in repo:
/home/josue/workspace/kernel/ai-agent-orchestrator-main

Follow:
- AGENTS.md
- codex_tasks/CODEX_RULES.md
- docs/hammer_radar/live_readiness/PHASE_INDEX.md
- docs/hammer_radar/live_readiness/TINY_LIVE_REAL_SUBMIT_OPERATOR_RUNBOOK.md
- docs/hammer_radar/live_readiness/R263_TINY_LIVE_FINAL_CONSOLE_LANE_INTELLIGENCE_CONTROLS_ARMING.md
- docs/hammer_radar/live_readiness/R262B_TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_TRIPLET.md
- docs/hammer_radar/live_readiness/R261_TINY_LIVE_CONTROLS_ARMING_UI_AND_API.md
- docs/hammer_radar/live_readiness/R260_TINY_LIVE_FRESH_CYCLE_ONE_SHOT_ORCHESTRATOR.md

PHASE:
R264 Tiny-Live Actual Submit and Immediate Reconciliation

BRANCH:
r264-tiny-live-actual-submit-immediate-reconciliation

PHASE CLASSIFICATION:
Primary: ACTUAL LIVE SUBMIT GATE / IMMEDIATE RECONCILIATION
Secondary: EXACT 3-ORDER BINANCE FUTURES SUBMIT, IDEMPOTENCY, PARTIAL SUCCESS HANDLING
Duplicate risk: EXTREME

WHY THIS PHASE EXISTS:
R263 Final Console has been committed.

R263 created:
- final console CLI
- final console API/UI
- lane/fisherman intelligence panel
- contract-fit panel from R262B
- signed triplet panel
- controls panel
- explicit experimental 8m short lane acceptance path
- runtime-only controls arming path
- R264 checkpoint requirement

Important R263 architecture:
- baseline repo lane_controls.json must remain paper for 8m short
- R263 runtime arming can temporarily mark BTCUSDT|8m|short|ladder_close_50_618 as tiny_live
- R263 arming must be explicit and logged
- R263 does NOT submit

R262B produced:
- valid percentage risk model
- isolated_risk_wallet_usdt=88
- resolved_position_margin_usdt=44
- leverage=10
- resolved_max_notional_usdt=440
- candidate_qty=0.006 BTC
- candidate_notional_usdt approximately 384-386
- candidate_margin_usdt approximately 38.4
- candidate_estimated_loss_usdt=4.44
- signed triplet available
- risk contract valid
- no live submit

R264 must implement the actual submit gate and immediate reconciliation.

ABSOLUTE BUILD RULE:
Codex must NOT execute a real live submit while building this phase.
Codex may implement the code path.
Codex may test via monkeypatched/local fake submit clients.
Codex may run preview/dry-run smoke.
Codex must NOT run --execute-actual-live-submit with real Binance order endpoint.
Codex must NOT use real credentials during tests.
Codex must NOT call Binance order/private/account/signed endpoints during build validation.

R264 must create a manual operator command that can later be run by the user/operator only after final verification.

OFFICIAL EXECUTION LANE:
BTCUSDT|8m|short|ladder_close_50_618

CURRENT KNOWN LANE CONTEXT:
- 8m short is paper-only / promotion-mismatched by strategy promotion config
- R263 explicit operator acceptance is required
- R263 runtime arming is required before live submit
- R263 baseline config should not be permanently armed in repo

PROMOTED LANES TO DISPLAY FOR CONTEXT:
- BTCUSDT|13m|long|ladder_close_50_618
- BTCUSDT|44m|long|ladder_close_50_618

ACTUAL SUBMIT ORDER REQUIREMENT:
Exactly three Binance Futures order requests:
1. main MARKET order
2. protective STOP_MARKET reduce-only order
3. TAKE_PROFIT_MARKET reduce-only order

No other orders.
No batch of extra orders.
No averaging.
No retry that creates duplicate main position.
No live submit if any idempotency check says a prior live submit exists.
No live submit if signed request stale.
No live submit if R263 arming missing.
No live submit if R262B contract fit invalid.
No live submit if exact confirmation phrase missing.
No live submit unless explicit --execute-actual-live-submit and --allow-binance-order-endpoint flags are both present.

EXACT LIVE SUBMIT CONFIRMATION PHRASE:
I CONFIRM TINY LIVE BTCUSDT 8M SHORT ACTUAL SUBMIT; USE LATEST R262B CONTRACT-FIT SIGNED TRIPLET ONLY; MAIN SELL MARKET 0.006 BTC; STOP BUY STOP_MARKET REDUCE_ONLY; TAKE_PROFIT BUY TAKE_PROFIT_MARKET REDUCE_ONLY; NO OTHER ORDERS.

EXACT DRY PREVIEW CONFIRMATION PHRASE:
I CONFIRM TINY LIVE R264 ACTUAL SUBMIT DRY PREVIEW ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL.

CORE INTENT:
Create a final actual submit gate that:
1. Loads latest R262B contract-fit signed triplet.
2. Loads latest R263 final console and controls arming record.
3. Validates R263 experimental-lane acceptance.
4. Validates controls are armed in the current runtime/config if required.
5. Validates latest signed triplet has exactly 3 requests.
6. Validates main order is SELL MARKET qty 0.006 BTC.
7. Validates stop is BUY STOP_MARKET reduce-only.
8. Validates take profit is BUY TAKE_PROFIT_MARKET reduce-only.
9. Validates all three requests match the same symbol/lane.
10. Validates risk contract remains valid.
11. Validates signed request freshness.
12. Validates no prior live submit exists for the same signed triplet/idempotency key.
13. Builds a dry-run preview by default.
14. Implements actual order submit only behind exact flags and exact phrase.
15. Records every attempt.
16. Immediately reconciles submitted order ids/statuses.
17. Handles partial success by recording a CRITICAL partial-success state and recovery instructions.
18. Never hides partial success.
19. Never places extra recovery orders automatically in R264.
20. Produces R265 recovery/hardening task.

NON-NEGOTIABLES:
- Default command is preview/dry only.
- No real Binance order endpoint in tests.
- No real Binance private/account endpoint in tests.
- No order submit unless:
  - --execute-actual-live-submit present
  - --allow-binance-order-endpoint present
  - exact live submit phrase matches
  - R263 arming accepted
  - R262B contract fit valid
  - signed triplet fresh
  - idempotency clean
- No submit if freshness expired.
- No submit if triplet count != 3.
- No submit if main/stop/tp shape mismatch.
- No submit if stop/tp are not reduce-only.
- No submit if risk contract invalid.
- No submit if lane controls are not armed for this exact lane.
- No submit if live_execution_enabled/global kill-switch requirements are unresolved by existing gates.
- No extra orders.
- No order cancellation in R264 unless already existing safe helper exists and is tested with fake client; prefer record recovery instructions, not auto-cancel.
- No .env write.
- No external env write.
- No secret printing.
- No secret persistence.
- No paper/live separation break.
- No strategy promotion mutation.
- No paper outcome mutation.
- No performance mutation.
- No sudo.
- Do not commit.
- Do not merge.
- Do not tag.
- Do not touch or stage AGENTS.md.

ALLOWED:
- Read local signed request artifacts.
- Read runtime credential source only in real-submit execution path, never preview/tests.
- Implement Binance Futures order submit client abstraction.
- Use fake submit client in tests.
- Record dry preview ledger.
- Record actual submit attempt ledger.
- Record actual submit reconciliation ledger.
- Add API/UI actual submit checkpoint card with no auto-submit.
- Add exact final command display.
- Add docs/tests.
- Create R265 future task.

REQUIRED MODULE:
Create:
src/app/hammer_radar/operator/tiny_live_actual_submit_reconciliation.py

Expose:
- build_tiny_live_actual_submit_reconciliation
- load_latest_r262b_contract_fit_record
- load_latest_r263_final_console_record
- load_latest_contract_fit_signed_triplet
- validate_r263_controls_armed
- validate_contract_fit_triplet_shape
- validate_contract_fit_risk
- validate_signed_triplet_freshness
- build_actual_submit_idempotency_key
- load_prior_actual_submit_records
- validate_no_duplicate_actual_submit
- build_actual_submit_preview_packet
- build_binance_futures_order_submit_client
- submit_exact_three_orders
- reconcile_exact_three_order_responses
- classify_partial_success_state
- build_partial_success_recovery_packet
- append_tiny_live_actual_submit_record
- load_tiny_live_actual_submit_records
- classify_tiny_live_actual_submit_status

CLIENT DESIGN:
Implement a submit client interface:
- In preview and tests: fake client only.
- In actual execution: real Binance Futures HTTP client only when --execute-actual-live-submit and --allow-binance-order-endpoint are present and confirmation matches.
- Real client must use existing credential source conventions.
- Real client must call only order endpoints needed for the three signed requests.
- Real client must not print secrets.
- Real client must redact auth/signature fields in output.

CLI:
Wire into inspect.py as:
tiny-live-actual-submit-reconcile

Args:
- --dry-run-actual-submit-reconcile
- --record-actual-submit-preview
- --confirm-actual-submit-dry-preview <phrase>
- --execute-actual-live-submit
- --allow-binance-order-endpoint
- --confirm-actual-live-submit <phrase>
- --operator-id <id> optional default local_operator
- --reason <text> optional

Preview:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-actual-submit-reconcile

Dry preview record:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-actual-submit-reconcile \
  --dry-run-actual-submit-reconcile \
  --record-actual-submit-preview \
  --confirm-actual-submit-dry-preview "I CONFIRM TINY LIVE R264 ACTUAL SUBMIT DRY PREVIEW ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL."

Rejected live submit:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-actual-submit-reconcile \
  --execute-actual-live-submit \
  --allow-binance-order-endpoint \
  --confirm-actual-live-submit "wrong"

Actual live submit command template, DO NOT RUN IN CODEX:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-actual-submit-reconcile \
  --execute-actual-live-submit \
  --allow-binance-order-endpoint \
  --confirm-actual-live-submit "I CONFIRM TINY LIVE BTCUSDT 8M SHORT ACTUAL SUBMIT; USE LATEST R262B CONTRACT-FIT SIGNED TRIPLET ONLY; MAIN SELL MARKET 0.006 BTC; STOP BUY STOP_MARKET REDUCE_ONLY; TAKE_PROFIT BUY TAKE_PROFIT_MARKET REDUCE_ONLY; NO OTHER ORDERS." \
  --operator-id local_operator \
  --reason "R264 actual tiny-live submit after R262B contract-fit and R263 final console arming."

STATUS ENUM:
- TINY_LIVE_ACTUAL_SUBMIT_RECONCILE_READY
- TINY_LIVE_ACTUAL_SUBMIT_DRY_PREVIEW_RECORDED
- TINY_LIVE_ACTUAL_SUBMIT_REJECTED
- TINY_LIVE_ACTUAL_SUBMIT_BLOCKED
- TINY_LIVE_ACTUAL_SUBMIT_EXECUTED_RECONCILED
- TINY_LIVE_ACTUAL_SUBMIT_PARTIAL_SUCCESS_CRITICAL
- TINY_LIVE_ACTUAL_SUBMIT_ERROR

OVERALL STATUS ENUM:
- TINY_LIVE_ACTUAL_SUBMIT_READY_FOR_DRY_PREVIEW
- TINY_LIVE_ACTUAL_SUBMIT_DRY_PREVIEW_RECORDED_READY_FOR_OPERATOR_DECISION
- TINY_LIVE_ACTUAL_SUBMIT_BLOCKED_BY_STALE_SIGNED_TRIPLET
- TINY_LIVE_ACTUAL_SUBMIT_BLOCKED_BY_MISSING_R263_ARMING
- TINY_LIVE_ACTUAL_SUBMIT_BLOCKED_BY_DUPLICATE_SUBMIT
- TINY_LIVE_ACTUAL_SUBMIT_BLOCKED_BY_RISK_CONTRACT
- TINY_LIVE_ACTUAL_SUBMIT_REJECTED_BAD_CONFIRMATION
- TINY_LIVE_ACTUAL_SUBMIT_EXECUTED_RECONCILED_ALL_THREE
- TINY_LIVE_ACTUAL_SUBMIT_PARTIAL_SUCCESS_NEEDS_RECOVERY
- UNKNOWN_NEEDS_MANUAL_REVIEW

OUTPUT MUST INCLUDE:
{
  "status": "...",
  "generated_at": "...",
  "dry_run_actual_submit_reconcile_requested": false,
  "record_actual_submit_preview_requested": false,
  "execute_actual_live_submit_requested": false,
  "allow_binance_order_endpoint": false,
  "confirmation_valid": false,
  "actual_submit_preview_recorded": false,
  "actual_submit_executed": false,
  "actual_submit_reconciled": false,
  "target_scope": {
    "official_lane_key": "BTCUSDT|8m|short|ladder_close_50_618",
    "symbol": "BTCUSDT",
    "timeframe": "8m",
    "direction": "short",
    "actual_submit_reconcile_gate": true,
    "order_placed": false
  },
  "input_summary": {
    "r262b_contract_fit_found": true/false,
    "r262b_contract_fit_valid": true/false,
    "r263_final_console_found": true/false,
    "r263_controls_armed": true/false,
    "signed_triplet_found": true/false,
    "signed_triplet_count": null
  },
  "pre_submit_validation": {
    "valid": true/false,
    "blocked_by": [],
    "signed_triplet_fresh": true/false,
    "signed_triplet_age_seconds": null,
    "risk_contract_valid": true/false,
    "controls_armed": true/false,
    "experimental_lane_acceptance_recorded": true/false,
    "duplicate_submit_found": true/false,
    "exact_three_orders": true/false,
    "main_order_valid": true/false,
    "stop_order_valid": true/false,
    "take_profit_order_valid": true/false,
    "reduce_only_exits": true/false
  },
  "order_triplet_summary": {
    "main": {
      "symbol": "BTCUSDT",
      "side": "SELL",
      "type": "MARKET",
      "quantity": "0.006"
    },
    "stop": {
      "symbol": "BTCUSDT",
      "side": "BUY",
      "type": "STOP_MARKET",
      "reduce_only": true,
      "stop_price": null
    },
    "take_profit": {
      "symbol": "BTCUSDT",
      "side": "BUY",
      "type": "TAKE_PROFIT_MARKET",
      "reduce_only": true,
      "stop_price": null
    }
  },
  "idempotency": {
    "actual_submit_idempotency_key": "...",
    "prior_live_submit_found": true/false,
    "prior_records_count": 0
  },
  "submit_plan": {
    "will_call_binance_order_endpoint": true/false,
    "will_place_exactly_three_orders": true/false,
    "will_place_main_market_order": true/false,
    "will_place_reduce_only_stop": true/false,
    "will_place_reduce_only_take_profit": true/false,
    "will_place_any_extra_orders": false
  },
  "submit_result": {
    "attempted": true/false,
    "main_submitted": true/false,
    "stop_submitted": true/false,
    "take_profit_submitted": true/false,
    "all_three_submitted": true/false,
    "order_ids": [],
    "client_order_ids": [],
    "errors": []
  },
  "reconciliation": {
    "attempted": true/false,
    "all_three_reconciled": true/false,
    "main_order_status": null,
    "stop_order_status": null,
    "take_profit_order_status": null,
    "partial_success": true/false,
    "critical": true/false,
    "recovery_required": true/false
  },
  "partial_success_recovery_packet": {
    "required": true/false,
    "reason": null,
    "operator_action": null,
    "do_not_resubmit_main": true/false,
    "suggested_next_phase": "R265_TINY_LIVE_POST_LIVE_HARDENING_AND_RECOVERY"
  },
  "actual_submit_go_no_go_packet": {
    "go_for_actual_live_submit_now": true/false,
    "operator_should_submit_now": false unless exact live command is already being executed,
    "next_required_step": "REFRESH_R262B|REARM_R263_RUNTIME|RUN_DRY_PREVIEW|OPERATOR_DECISION|R265_RECOVERY|WAIT|FIX_BLOCKER"
  },
  "actual_submit_matrix": {
    "r262b_valid": true/false,
    "r263_armed": true/false,
    "signed_triplet_fresh": true/false,
    "idempotency_clean": true/false,
    "exact_confirmation": true/false,
    "allow_order_endpoint": true/false,
    "executed": true/false,
    "reconciled": true/false,
    "partial_success": true/false,
    "blocked_by": []
  },
  "actual_submit_overall_status": "...",
  "recommended_next_operator_move": "...",
  "recommended_next_engineering_move": "...",
  "do_not_run_yet": [
    "duplicate actual submit",
    "actual submit with stale signed triplet",
    "actual submit without R263 arming",
    "actual submit without exact phrase",
    "actual submit if prior live submit exists"
  ],
  "safety": {...}
}

SAFETY OBJECT MUST INCLUDE:
- env_written=false
- env_mutated=false
- external_env_file_written=false
- risk_contract_config_written=false
- lane_controls_written=false
- live_config_written=false
- actual_submit_reconcile_gate=true
- hmac_signature_created=false in preview/tests; true only if real client signs internally as part of existing signed request flow, but should generally use existing signed triplet
- signed_request_written=false
- signed_order_request_created=false
- signed_trading_request_created=false
- submit_allowed=true only inside actual live submit execution path after all validations and exact flags
- submit_attempted=true only inside actual live submit execution path
- order_placed=true only if at least one real Binance order response succeeds
- real_order_placed=true only if at least one real Binance order response succeeds
- execution_attempted=true only inside actual live submit execution path
- binance_order_endpoint_called=true only inside actual live submit execution path
- binance_test_order_endpoint_called=false
- binance_account_endpoint_called=false unless a reconciliation helper explicitly requires it; prefer not
- binance_exchange_info_endpoint_called=false
- binance_mark_price_endpoint_called=false
- private_binance_endpoint_called=true only inside actual live submit execution path
- signed_binance_endpoint_called=true only inside actual live submit execution path
- network_allowed=true only inside actual live submit execution path
- transfer_endpoint_called=false
- withdraw_endpoint_called=false
- kill_switch_disabled=false
- live_controls_armed_by_phase=false
- secrets_read=true only inside actual live submit execution path
- secrets_shown=false
- secrets_persisted=false
- secret_values_in_output=false
- global_live_flags_changed=false
- paper_live_separation_intact=true
- official_tiny_live_lane_changed=false

LEDGER:
logs/hammer_radar_forward/tiny_live_actual_submit_reconciliation.ndjson

API/UI:
Add endpoints to approval_api.py:
- GET /tiny-live/actual-submit/reconcile
- POST /tiny-live/actual-submit/dry-preview
- POST /tiny-live/actual-submit/execute

UI card:
- Add Tiny Live Actual Submit Checkpoint card.
- Show pre-submit validation.
- Show triplet.
- Show idempotency.
- Show reconciliation status.
- Show partial success recovery packet.
- Show exact live command text.
- Do not auto-submit.
- If execute endpoint exists, it must require exact phrase and explicit allow flag.

DOCS:
Create:
docs/hammer_radar/live_readiness/R264_TINY_LIVE_ACTUAL_SUBMIT_AND_IMMEDIATE_RECONCILIATION.md

Update:
docs/hammer_radar/live_readiness/R263_TINY_LIVE_FINAL_CONSOLE_LANE_INTELLIGENCE_CONTROLS_ARMING.md
docs/hammer_radar/live_readiness/TINY_LIVE_REAL_SUBMIT_OPERATOR_RUNBOOK.md
docs/hammer_radar/live_readiness/PHASE_INDEX.md

FUTURE TASK:
Create:
codex_tasks/phases/R265_TINY_LIVE_POST_LIVE_HARDENING_AND_RECOVERY.md

R265 must:
- inspect actual submit/reconciliation ledger
- inspect partial success state
- provide recovery command packets
- add dashboard recovery state
- add re-entry lock
- no extra live order unless a separate exact recovery phrase exists

TESTS:
Create:
tests/hammer_radar/test_tiny_live_actual_submit_reconciliation.py

Tests must cover:
- CLI preview returns JSON
- dry preview record writes ledger but no network/order/submit
- wrong live confirmation rejects
- missing --allow-binance-order-endpoint rejects
- stale signed triplet blocks
- missing R263 arming blocks
- duplicate submit blocks
- wrong triplet count blocks
- main order shape mismatch blocks
- stop/tp reduce-only mismatch blocks
- fake client successful exact three submit records all three
- fake client partial success records critical recovery packet
- no extra orders on partial success
- no real Binance calls in tests
- no secrets in output
- API GET checkpoint returns JSON
- API execute requires exact phrase and allow flag
- UI contains warning and no auto-submit behavior

VALIDATION:
Run py_compile:
- src/app/hammer_radar/operator/tiny_live_actual_submit_reconciliation.py
- src/app/hammer_radar/operator/tiny_live_final_console.py
- src/app/hammer_radar/operator/approval_api.py
- src/app/hammer_radar/operator/inspect.py

Run focused:
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar/test_tiny_live_actual_submit_reconciliation.py

Run related:
PYTHONPATH=. .venv/bin/python -m pytest -q \
  tests/hammer_radar/test_tiny_live_final_console.py \
  tests/hammer_radar/test_tiny_live_percentage_risk_contract_fit_regeneration.py \
  tests/hammer_radar/test_tiny_live_controls_arming.py \
  tests/hammer_radar/test_tiny_live_actual_submit_gate.py

Run full:
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar

SMOKE:
Preview:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-actual-submit-reconcile \
  | jq '.status, .target_scope, .input_summary, .pre_submit_validation, .order_triplet_summary, .idempotency, .submit_plan, .submit_result, .reconciliation, .partial_success_recovery_packet, .actual_submit_go_no_go_packet, .actual_submit_matrix, .actual_submit_overall_status, .recommended_next_operator_move, .recommended_next_engineering_move, .do_not_run_yet, .safety'

Dry preview record:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-actual-submit-reconcile \
  --dry-run-actual-submit-reconcile \
  --record-actual-submit-preview \
  --confirm-actual-submit-dry-preview "I CONFIRM TINY LIVE R264 ACTUAL SUBMIT DRY PREVIEW ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL." \
  | jq '.status, .actual_submit_preview_recorded, .pre_submit_validation, .idempotency, .actual_submit_go_no_go_packet, .actual_submit_matrix, .actual_submit_overall_status, .safety'

Rejected live:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-actual-submit-reconcile \
  --execute-actual-live-submit \
  --allow-binance-order-endpoint \
  --confirm-actual-live-submit "wrong" \
  | jq '.status, .confirmation_valid, .actual_submit_executed, .submit_result, .safety'

Secret leak check:
PYTHONPATH=. .venv/bin/python - <<'PY'
import os
from pathlib import Path

paths = [
    Path("logs/hammer_radar_forward/tiny_live_actual_submit_reconciliation.ndjson"),
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
git diff -- configs/hammer_radar/lane_controls.json || true
git diff -- configs/hammer_radar/tiny_live_risk_contracts.json || true
git diff -- logs/hammer_radar_forward/candles_BTCUSDT_8m.ndjson || true
git diff -- logs/hammer_radar_forward/paper_outcomes.ndjson || true
git diff -- logs/hammer_radar_forward/strategy_performance.ndjson || true
git diff -- logs/hammer_radar_forward/strategy_promotion_status.ndjson || true

Expected artifacts:
git status --short logs/hammer_radar_forward/tiny_live_actual_submit_reconciliation.ndjson || true
tail -n 5 logs/hammer_radar_forward/tiny_live_actual_submit_reconciliation.ndjson 2>/dev/null || true

FINAL PHASE REPORT REQUIRED:
At the end, report:
- phase status
- files changed
- tests run
- smoke status
- safety status
- input_summary
- pre_submit_validation
- order_triplet_summary
- idempotency
- submit_plan
- submit_result
- reconciliation
- partial_success_recovery_packet
- actual_submit_go_no_go_packet
- actual_submit_matrix
- actual_submit_overall_status
- API/UI endpoints added
- exact files mutated
- recommended next operator move
- recommended next engineering move
- do not commit
- do not run real submit

Aggressive mode:
Complete in one pass.
Implement actual submit gate but do not execute real submit.
Use fake clients for tests.
Do not call real Binance order/private/account endpoints.
Do not place orders during Codex validation.
