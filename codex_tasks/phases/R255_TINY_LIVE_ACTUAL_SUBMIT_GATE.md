You are in repo:
/home/josue/workspace/kernel/ai-agent-orchestrator-main

Follow:
- AGENTS.md
- codex_tasks/CODEX_RULES.md
- docs/hammer_radar/live_readiness/PHASE_INDEX.md

PHASE:
R255 Tiny-Live Actual Submit Gate Implementation

BRANCH:
r255-tiny-live-actual-submit-gate-implementation

PHASE CLASSIFICATION:
Primary: ACTUAL SUBMIT GATE IMPLEMENTATION
Secondary: LIVE ORDER SAFETY, IDEMPOTENCY, ENDPOINT ALLOWLIST, POST-SUBMIT RECONCILIATION
Duplicate risk: EXTREME

IMPORTANT:
This phase implements the actual tiny-live submit gate, but Codex must NOT execute a live submit during implementation.

Codex may:
- build submit gate code
- build tests
- build dry preview
- build blocked default behavior
- build exact confirmation handling
- build ledger schemas
- build post-submit reconciliation scaffolding
- prove rejected/wrong confirmations do not submit

Codex must NOT:
- call Binance order endpoint during this phase run
- place live order
- execute final submit command
- use the R255 live confirmation phrase during smoke
- set submit_allowed=true by default
- send network traffic except in unit tests with mocks

The actual live submit command will be run manually by operator later, after review.

WHY THIS PHASE EXISTS:
R254 Tiny-Live Submit Gate Preview has been committed.

R254 confirmed:
- latest R253B fresh signed request exists
- signed_requests_count=3
- all signatures are 64 hex
- order triplet is valid:
  - main SELL MARKET 0.007
  - stop BUY STOP_MARKET reduceOnly true stopPrice 64309.3
  - take-profit BUY TAKE_PROFIT_MARKET reduceOnly true stopPrice 62406.4
- submit_allowed=false
- order_placed=false
- network_allowed=false
- binance_order_endpoint_called=false
- future R255 confirmation phrase was generated

R255 must implement the first actual live submit gate, but keep it impossible to accidentally execute.

OFFICIAL LANE:
BTCUSDT|8m|short|ladder_close_50_618

EXPECTED LATEST ORDER TRIPLET FROM R253B/R254:
- main order:
  - endpoint: POST /fapi/v1/order
  - side: SELL
  - type: MARKET
  - quantity: 0.007
- stop order:
  - endpoint: POST /fapi/v1/order
  - side: BUY
  - type: STOP_MARKET
  - quantity: 0.007
  - stopPrice: 64309.3
  - reduceOnly: true
  - workingType: MARK_PRICE
- take-profit order:
  - endpoint: POST /fapi/v1/order
  - side: BUY
  - type: TAKE_PROFIT_MARKET
  - quantity: 0.007
  - stopPrice: 62406.4
  - reduceOnly: true
  - workingType: MARK_PRICE

R255 FUTURE LIVE CONFIRMATION PHRASE:
I CONFIRM TINY LIVE BTCUSDT 8M SHORT SUBMIT ONLY; PLACE EXACTLY THREE BINANCE FUTURES ORDERS FROM LATEST R253B SIGNED REQUEST; MAIN SELL MARKET 0.007 BTC; STOP BUY STOP_MARKET REDUCE_ONLY; TAKE_PROFIT BUY TAKE_PROFIT_MARKET REDUCE_ONLY; NO OTHER ORDERS.

Do not run this phrase during Codex implementation.
Only include it as metadata and rejected-by-default unless user manually runs the command later.

CORE INTENT:
Create an actual submit gate module that can eventually submit exactly three Binance Futures orders from the latest R253B signed request artifact, but only when all gates pass and only under exact operator confirmation.

The module must enforce:
1. Latest R254 submit gate preview exists and is recorded.
2. Latest R253B fresh regeneration exists and is valid.
3. Latest R253B signed request artifact exists and is valid.
4. Latest signed request was created by R253B.
5. Signed request age / timestamp freshness check exists.
6. If signed request is stale, block and request regeneration.
7. Runtime credential source is available, but secrets are not printed.
8. Kill switch / lane control permits tiny-live submit.
9. Endpoint allowlist is exactly POST /fapi/v1/order.
10. Exactly three orders are intended.
11. Order sequence is:
    - main order first
    - stop order second
    - take-profit order third
12. Idempotency/dedupe blocks if same signal/lane submit already recorded.
13. Max loss and notional are still within tiny-live risk contract.
14. R255 exact confirmation phrase matches.
15. A dry preview mode exists and is the default.
16. Live submit mode is impossible without exact phrase and explicit flag.
17. Post-submit reconciliation plan/ledger is prepared.

This phase should implement the submit machinery and safety walls.
It must not perform actual submit during Codex execution.

NON-NEGOTIABLES:
- No live Binance order endpoint calls during Codex run.
- No actual order placement during Codex run.
- No submit during tests/smoke unless mocked.
- No private/account endpoint during tests/smoke unless mocked.
- No accidental network call in tests.
- No submit_allowed=true by default.
- No order_placed=true without mocked submit or later real submit.
- No API key printing.
- No API secret printing.
- No secrets in stdout/stderr/logs/artifacts.
- No .env write.
- No external env file write.
- No lane_controls.json write.
- No risk contract config write.
- No kill switch disable.
- No global live flag changes.
- No paper_outcomes append.
- No strategy performance append.
- No strategy promotion status append.
- No betrayal promotion.
- No alternate lane promotion.
- No official lane change.
- No sudo.
- Do not commit.
- Do not merge.
- Do not tag.
- Do not touch or stage AGENTS.md.

ALLOWED:
- Read local ledgers/configs.
- Build R255 actual submit gate module.
- Add CLI command.
- Add tests with mocked Binance client/session.
- Append R255 dry preview ledger under preview confirmation.
- Append R255 rejected ledger under bad confirmation if useful.
- Prepare but do not execute final live submit command.

FORBIDDEN IN THIS CODEX RUN:
- Real network call to Binance order endpoint.
- Real POST /fapi/v1/order.
- Real order placement.
- Real submit.
- Using the future live confirmation phrase in a real submit command.

REQUIRED MODULE:
Create:
src/app/hammer_radar/operator/tiny_live_actual_submit_gate.py

Expose:
- build_tiny_live_actual_submit_gate
- load_latest_tiny_live_submit_gate_preview
- load_latest_tiny_live_fresh_context_signed_request_regeneration_gate
- load_latest_tiny_live_signed_request_write_gate
- load_latest_tiny_live_executable_payload_write_gate
- load_latest_tiny_live_stop_take_profit_source_gate
- validate_r254_submit_gate_preview_ready
- validate_latest_r253b_signed_request_for_actual_submit
- validate_signed_request_timestamp_freshness
- validate_runtime_credential_source_for_submit
- validate_kill_switch_and_lane_controls_for_tiny_live_submit
- validate_order_endpoint_allowlist
- validate_exactly_three_order_triplet
- validate_order_sequence_main_stop_take_profit
- validate_tiny_live_risk_contract_still_within_bounds
- build_idempotency_key_for_tiny_live_submit
- validate_no_prior_live_submit_for_idempotency_key
- build_actual_submit_plan
- build_actual_submit_dry_run_preview
- build_post_submit_reconciliation_plan
- execute_actual_submit_with_injected_client
- build_actual_submit_gate_matrix
- build_operator_actual_submit_gate_packet
- classify_tiny_live_actual_submit_gate_status
- append_tiny_live_actual_submit_gate_record
- load_tiny_live_actual_submit_gate_records
- summarize_tiny_live_actual_submit_gate_records

CLI:
Wire into inspect.py as:
tiny-live-actual-submit-gate

Args:
- --dry-run-actual-submit-gate
- --record-actual-submit-gate-preview
- --confirm-tiny-live-actual-submit-gate-preview <phrase>
- --execute-actual-submit
- --confirm-tiny-live-actual-submit <phrase>
- --allow-real-binance-order-endpoint

Default behavior:
- preview only
- no network
- no order endpoint
- no submit
- no order

Preview command:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-actual-submit-gate

Record dry actual-submit gate preview:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-actual-submit-gate \
  --dry-run-actual-submit-gate \
  --record-actual-submit-gate-preview \
  --confirm-tiny-live-actual-submit-gate-preview "I CONFIRM TINY LIVE ACTUAL SUBMIT GATE DRY PREVIEW ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL."

Rejected real submit attempt:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-actual-submit-gate \
  --execute-actual-submit \
  --confirm-tiny-live-actual-submit "wrong"

Do NOT run the real submit command during this phase.

DRY PREVIEW CONFIRMATION PHRASE:
I CONFIRM TINY LIVE ACTUAL SUBMIT GATE DRY PREVIEW ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL.

REAL SUBMIT CONFIRMATION PHRASE:
I CONFIRM TINY LIVE BTCUSDT 8M SHORT SUBMIT ONLY; PLACE EXACTLY THREE BINANCE FUTURES ORDERS FROM LATEST R253B SIGNED REQUEST; MAIN SELL MARKET 0.007 BTC; STOP BUY STOP_MARKET REDUCE_ONLY; TAKE_PROFIT BUY TAKE_PROFIT_MARKET REDUCE_ONLY; NO OTHER ORDERS.

REAL SUBMIT MUST REQUIRE ALL THREE:
- --execute-actual-submit
- --allow-real-binance-order-endpoint
- exact real submit confirmation phrase

But tests/smoke must not run this real submit path against network.

STATUS ENUM:
- TINY_LIVE_ACTUAL_SUBMIT_GATE_READY
- TINY_LIVE_ACTUAL_SUBMIT_GATE_DRY_PREVIEW_RECORDED
- TINY_LIVE_ACTUAL_SUBMIT_GATE_REJECTED
- TINY_LIVE_ACTUAL_SUBMIT_GATE_BLOCKED
- TINY_LIVE_ACTUAL_SUBMIT_GATE_MOCK_SUBMITTED
- TINY_LIVE_ACTUAL_SUBMIT_GATE_REAL_SUBMIT_READY_BUT_NOT_EXECUTED
- TINY_LIVE_ACTUAL_SUBMIT_GATE_ERROR

OVERALL STATUS ENUM:
- TINY_LIVE_ACTUAL_SUBMIT_GATE_READY_FOR_DRY_PREVIEW
- TINY_LIVE_ACTUAL_SUBMIT_GATE_DRY_PREVIEW_RECORDED_AWAITING_OPERATOR_REAL_SUBMIT
- TINY_LIVE_ACTUAL_SUBMIT_GATE_REJECTED_BAD_CONFIRMATION
- TINY_LIVE_ACTUAL_SUBMIT_GATE_BLOCKED_BY_MISSING_R254
- TINY_LIVE_ACTUAL_SUBMIT_GATE_BLOCKED_BY_INVALID_SIGNED_REQUEST
- TINY_LIVE_ACTUAL_SUBMIT_GATE_BLOCKED_BY_STALE_TIMESTAMP
- TINY_LIVE_ACTUAL_SUBMIT_GATE_BLOCKED_BY_KILL_SWITCH
- TINY_LIVE_ACTUAL_SUBMIT_GATE_BLOCKED_BY_IDEMPOTENCY
- TINY_LIVE_ACTUAL_SUBMIT_GATE_BLOCKED_BY_RISK_CONTRACT
- TINY_LIVE_ACTUAL_SUBMIT_GATE_BLOCKED_BY_ENDPOINT_SAFETY
- TINY_LIVE_ACTUAL_SUBMIT_GATE_MOCK_SUBMITTED_FOR_TEST_ONLY
- UNKNOWN_NEEDS_MANUAL_REVIEW

OUTPUT MUST INCLUDE:
{
  "status": "...",
  "generated_at": "...",
  "dry_run_actual_submit_gate_requested": false,
  "record_actual_submit_gate_preview_requested": false,
  "execute_actual_submit_requested": false,
  "allow_real_binance_order_endpoint": false,
  "preview_confirmation_valid": false,
  "real_submit_confirmation_valid": false,
  "actual_submit_executed": false,
  "target_scope": {
    "official_lane_key": "BTCUSDT|8m|short|ladder_close_50_618",
    "symbol": "BTCUSDT",
    "timeframe": "8m",
    "direction": "short",
    "actual_submit_gate": true,
    "dry_preview_only": true,
    "submit_allowed": false,
    "order_placed": false,
    "binance_order_endpoint_called": false,
    "network_allowed": false
  },
  "input_summary": {
    "r254_submit_gate_preview_found": true/false,
    "r254_submit_gate_preview_valid": true/false,
    "r253b_fresh_regeneration_found": true/false,
    "r253b_signed_request_found": true/false,
    "r253b_signed_request_valid": true/false,
    "r253b_payload_found": true/false,
    "r253b_stop_take_profit_found": true/false
  },
  "signed_request_freshness": {
    "timestamp_present": true/false,
    "signed_request_age_seconds": null,
    "max_allowed_age_seconds": 60,
    "fresh_enough_for_real_submit": true/false,
    "requires_regeneration": true/false
  },
  "runtime_credential_source_summary": {
    "credential_source_ready": true/false,
    "source_type": "external_env_file|process_env|none",
    "secrets_shown": false,
    "secrets_persisted": false
  },
  "kill_switch_lane_control_summary": {
    "kill_switch_allows_tiny_live": true/false,
    "official_lane_allowed": true/false,
    "live_execution_enabled": true/false,
    "blocked_by": []
  },
  "endpoint_allowlist_summary": {
    "valid": true/false,
    "allowed_endpoint": "/fapi/v1/order",
    "all_orders_use_allowed_endpoint": true/false,
    "forbidden_endpoint_detected": false,
    "private_account_endpoint_detected": false
  },
  "order_triplet_summary": {
    "exactly_three_orders": true/false,
    "sequence_valid": true/false,
    "main_order": {
      "side": "SELL",
      "type": "MARKET",
      "quantity": 0.007
    },
    "stop_order": {
      "side": "BUY",
      "type": "STOP_MARKET",
      "quantity": 0.007,
      "stopPrice": 64309.3,
      "reduceOnly": true
    },
    "take_profit_order": {
      "side": "BUY",
      "type": "TAKE_PROFIT_MARKET",
      "quantity": 0.007,
      "stopPrice": 62406.4,
      "reduceOnly": true
    }
  },
  "risk_contract_submit_summary": {
    "max_loss_usdt": 4.44,
    "estimated_loss_usdt": 4.4401,
    "notional_usdt": 445.725,
    "within_tiny_live_contract": true/false,
    "warnings": []
  },
  "idempotency_summary": {
    "idempotency_key": "...",
    "prior_live_submit_found": true/false,
    "dedupe_allows_submit": true/false
  },
  "actual_submit_plan": {
    "would_submit_exactly_three_orders": true/false,
    "submit_order_sequence": [
      "main_order",
      "stop_order",
      "take_profit_order"
    ],
    "submit_in_this_invocation": false,
    "requires_real_submit_confirmation": true,
    "requires_allow_real_binance_order_endpoint_flag": true
  },
  "post_submit_reconciliation_plan": {
    "required": true,
    "must_record_exchange_order_ids": true,
    "must_record_order_statuses": true,
    "must_verify_reduce_only_exits": true,
    "must_reconcile_main_stop_take_profit_triplet": true
  },
  "actual_submit_gate_matrix": {
    "r254_ready": true/false,
    "signed_request_valid": true/false,
    "timestamp_fresh_enough": true/false,
    "runtime_credentials_ready": true/false,
    "kill_switch_allows": true/false,
    "endpoint_allowlist_valid": true/false,
    "order_triplet_valid": true/false,
    "risk_contract_valid": true/false,
    "idempotency_allows": true/false,
    "preview_confirmed": true/false,
    "real_submit_confirmed": true/false,
    "allow_real_endpoint_flag": false,
    "submit_allowed": false,
    "order_placed": false,
    "blocked_by": []
  },
  "operator_actual_submit_gate_packet": {
    "operator_should_review_actual_submit_gate": true/false,
    "operator_should_regenerate_if_timestamp_stale": true/false,
    "operator_should_not_submit_from_codex": true,
    "operator_should_submit_now": false,
    "operator_should_place_order": false,
    "next_required_human_action": "REVIEW_R255_DRY_PREVIEW|REGENERATE_SIGNED_REQUEST|MANUAL_OPERATOR_DECISION_REQUIRED|WAIT|FIX_BLOCKER",
    "explicit_non_actions": [
      "do not place order from Codex implementation run",
      "do not submit without manual operator decision",
      "do not call Binance order endpoint from tests"
    ]
  },
  "recommended_next_operator_move": "...",
  "recommended_next_engineering_move": "...",
  "actual_submit_gate_overall_status": "...",
  "do_not_run_yet": [
    "unreviewed live submit",
    "duplicate live submit",
    "any non-/fapi/v1/order endpoint",
    "kill switch disable",
    "transfer",
    "withdraw",
    "betrayal live promotion"
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
- actual_submit_gate=true
- dry_preview_only=true unless real submit path explicitly invoked
- hmac_signature_created=false
- signed_request_written=false
- signed_order_request_created=false
- signed_trading_request_created=false
- submit_allowed=false during default/preview/codex run
- submit_attempted=false during default/preview/codex run
- order_placed=false during default/preview/codex run
- real_order_placed=false during default/preview/codex run
- execution_attempted=false during default/preview/codex run
- binance_order_endpoint_called=false during default/preview/codex run
- binance_test_order_endpoint_called=false
- binance_account_endpoint_called=false
- binance_exchange_info_endpoint_called=false
- binance_mark_price_endpoint_called=false
- private_binance_endpoint_called=false
- signed_binance_endpoint_called=false
- network_allowed=false during default/preview/codex run
- transfer_endpoint_called=false
- withdraw_endpoint_called=false
- kill_switch_disabled=false
- secrets_read=false unless exact real submit path resolves credentials later
- secrets_shown=false
- secrets_persisted=false
- secret_values_in_output=false
- global_live_flags_changed=false
- paper_live_separation_intact=true
- official_tiny_live_lane_changed=false

LEDGER:
logs/hammer_radar_forward/tiny_live_actual_submit_gate.ndjson

Only append dry preview record under dry preview exact confirmation phrase.
Do not append real submit record in Codex run unless using mocked submit tests.

TESTS:
Create:
tests/hammer_radar/test_tiny_live_actual_submit_gate.py

Tests must cover:
- CLI exists and returns JSON
- default preview makes no network call
- default preview does not submit
- dry preview exact confirmation records preview only
- wrong confirmation rejects
- real submit path rejects without exact real phrase
- real submit path rejects without --allow-real-binance-order-endpoint
- real submit path rejects stale signed timestamp
- endpoint allowlist rejects non-/fapi/v1/order
- blocks if order count is not exactly 3
- blocks if order sequence invalid
- blocks if idempotency prior submit exists
- blocks if kill switch disallows
- blocks if risk contract invalid
- mock submit test can inject fake client and record MOCK_SUBMITTED_FOR_TEST_ONLY without network
- no real network call in tests
- no real order placed in tests
- no secret values in output
- no env/config/lane_controls mutation

VALIDATION:
Run py_compile:
- src/app/hammer_radar/operator/tiny_live_actual_submit_gate.py
- src/app/hammer_radar/operator/inspect.py

Run focused test:
- tests/hammer_radar/test_tiny_live_actual_submit_gate.py

Run related tests:
- tests/hammer_radar/test_tiny_live_submit_gate_preview.py
- tests/hammer_radar/test_tiny_live_fresh_context_signed_request_regeneration_gate.py
- tests/hammer_radar/test_tiny_live_signed_request_runtime_source_write_gate.py
- tests/hammer_radar/test_tiny_live_signed_request_write_gate.py
- tests/hammer_radar/test_tiny_live_executable_payload_write_gate.py
- tests/hammer_radar/test_tiny_live_stop_take_profit_source_gate.py

Run full:
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar

SMOKE:
Preview:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-actual-submit-gate \
  | jq '.status, .target_scope, .input_summary, .signed_request_freshness, .runtime_credential_source_summary, .kill_switch_lane_control_summary, .endpoint_allowlist_summary, .order_triplet_summary, .risk_contract_submit_summary, .idempotency_summary, .actual_submit_plan, .post_submit_reconciliation_plan, .actual_submit_gate_matrix, .operator_actual_submit_gate_packet, .actual_submit_gate_overall_status, .recommended_next_operator_move, .recommended_next_engineering_move, .do_not_run_yet, .safety'

Dry preview record:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-actual-submit-gate \
  --dry-run-actual-submit-gate \
  --record-actual-submit-gate-preview \
  --confirm-tiny-live-actual-submit-gate-preview "I CONFIRM TINY LIVE ACTUAL SUBMIT GATE DRY PREVIEW ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL." \
  | jq '.status, .actual_submit_executed, .actual_submit_gate_matrix, .operator_actual_submit_gate_packet, .actual_submit_gate_overall_status, .safety'

Rejected real submit:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-actual-submit-gate \
  --execute-actual-submit \
  --confirm-tiny-live-actual-submit "wrong" \
  | jq '.status, .real_submit_confirmation_valid, .actual_submit_executed, .actual_submit_gate_matrix, .safety'

Do NOT run the real submit confirmation phrase during Codex implementation.

Secret leak check:
PYTHONPATH=. .venv/bin/python - <<'PY'
import os
from pathlib import Path

path = Path("logs/hammer_radar_forward/tiny_live_actual_submit_gate.ndjson")
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
git status --short logs/hammer_radar_forward/tiny_live_actual_submit_gate.ndjson || true
tail -n 3 logs/hammer_radar_forward/tiny_live_actual_submit_gate.ndjson 2>/dev/null || true

FINAL PHASE REPORT REQUIRED:
At the end, report:
- phase status
- files changed
- tests run
- smoke status
- safety status
- input_summary
- signed_request_freshness
- runtime_credential_source_summary
- kill_switch_lane_control_summary
- endpoint_allowlist_summary
- order_triplet_summary
- risk_contract_submit_summary
- idempotency_summary
- actual_submit_plan
- post_submit_reconciliation_plan
- actual_submit_gate_matrix
- operator_actual_submit_gate_packet
- actual_submit_gate_overall_status
- exact files mutated
- recommended next operator move
- recommended next engineering move
- do not commit
- do not run real submit phrase

DOCS:
Create:
docs/hammer_radar/live_readiness/R255_TINY_LIVE_ACTUAL_SUBMIT_GATE.md

Update:
docs/hammer_radar/live_readiness/PHASE_INDEX.md

FUTURE TASK:
Create:
codex_tasks/phases/R256_TINY_LIVE_OPERATOR_REAL_SUBMIT_RUNBOOK_AND_RECONCILIATION.md

R256 should:
- be an operator runbook/reconciliation phase after R255 dry implementation is validated
- include final manual pre-submit checklist
- include exact submit command but not auto-run it
- include post-submit exchange reconciliation and abort paths
- include duplicate protection review
- include what to do if only some of the three orders are accepted
- include immediate kill-switch/cleanup instructions

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
Do not run the real submit confirmation phrase.
Only record actual-submit dry preview if exact dry preview confirmation command is explicitly run.
