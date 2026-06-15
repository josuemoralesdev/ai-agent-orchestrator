You are in repo:
/home/josue/workspace/kernel/ai-agent-orchestrator-main

Follow:
- AGENTS.md
- codex_tasks/CODEX_RULES.md
- docs/hammer_radar/live_readiness/PHASE_INDEX.md
- docs/hammer_radar/live_readiness/TINY_LIVE_REAL_SUBMIT_OPERATOR_RUNBOOK.md
- docs/hammer_radar/live_readiness/R264_TINY_LIVE_ACTUAL_SUBMIT_AND_IMMEDIATE_RECONCILIATION.md
- docs/hammer_radar/live_readiness/R263_TINY_LIVE_FINAL_CONSOLE_LANE_INTELLIGENCE_CONTROLS_ARMING.md
- docs/hammer_radar/live_readiness/R262B_TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_TRIPLET.md

PHASE:
R264B Tiny-Live JIT Launch Packet

BRANCH:
r264b-tiny-live-jit-launch-packet

PHASE CLASSIFICATION:
Primary: JUST-IN-TIME LIVE LAUNCH PACKET
Secondary: FRESH TRIPLET, RUNTIME ARMING, DRY SUBMIT PREVIEW, FINAL MANUAL COMMAND
Duplicate risk: EXTREME

WHY THIS PHASE EXISTS:
R264 actual submit reconciliation gate has been implemented and committed.

R264 correctly blocked live submit because runtime state was stale/unarmed:
- signed_triplet_stale
- lane_controls_not_armed_tiny_live
- risk_contract_config_invalid or unresolved because the stale triplet/runtime state was not current

The operator wants tiny live tonight or early morning.

The correct compression is not more architecture.
The correct compression is a JIT launch packet that performs the final safe preparation steps in one operator command:
1. refresh R262B contract-fit signed triplet
2. runtime-arm R263 final console controls with experimental lane acceptance
3. run R264 dry preview
4. produce the exact live submit command
5. still do NOT execute live submit from Codex

This phase must make the path operational tonight.

R264B must not submit automatically.
R264B must not place any order.
R264B must not call Binance order endpoint.
R264B may call public readonly refresh and local signing through existing R262B logic under exact confirmation.
R264B may runtime-arm lane controls through existing R263 logic under exact confirmation.
R264B may record R264 dry preview under exact confirmation.
R264B must print a final command that the human operator can run manually only if the final packet says GO.

OFFICIAL EXECUTION LANE:
BTCUSDT|8m|short|ladder_close_50_618

KNOWN OPERATOR RISK MODEL:
- isolated risk wallet: 88 USDT
- position margin target: 44 USDT
- leverage: 10x
- position margin = 50% of isolated wallet
- wallet buffer = remaining 50%
- resolved max notional <= 440 USDT
- max loss <= 4.44 USDT
- current contract-fit quantity expected around 0.006 BTC depending fresh mark

LANE CONTEXT:
- 8m short is paper-only / promotion-mismatched by default
- R263 requires explicit experimental-lane acceptance
- this is allowed only as a manual experimental tiny-live lane
- promoted lanes remain 13m long and 44m long
- R264B must display this warning but may proceed if exact acceptance phrase is used

ABSOLUTE BUILD RULE:
Codex must NOT execute real live submit.
Codex must NOT run the final live command.
Codex must NOT call Binance order endpoint.
Codex must NOT call private/account/order endpoints.
Codex may run preview/JIT prep only.

CORE INTENT:
Create one CLI/API/UI command that:
1. Performs R262B fresh contract-fit regeneration.
2. Confirms signed triplet is fresh and risk-valid.
3. Performs R263 runtime-only final console controls arming.
4. Confirms experimental lane acceptance is recorded.
5. Performs R264 dry preview.
6. Confirms R264 dry preview has:
   - exact 3 orders
   - main SELL MARKET
   - stop BUY STOP_MARKET reduce-only
   - TP BUY TAKE_PROFIT_MARKET reduce-only
   - idempotency clean
   - no prior live submit
   - signed triplet fresh
   - risk valid
   - controls armed
7. Produces final human-run live command.
8. Records JIT launch packet ledger.
9. Does not submit.
10. Does not place order.

NON-NEGOTIABLES:
- No actual live submit in R264B.
- No Binance order endpoint.
- No Binance test order endpoint.
- No Binance account/private endpoint.
- No signed Binance endpoint.
- No order placement.
- No final live command execution by Codex.
- No full wallet 88 USDT position margin.
- No leverage above 10.
- No max notional above resolved contract.
- No risk loosening.
- No duplicate submit.
- No .env write.
- No external env write.
- No secrets printed.
- No secrets persisted.
- No strategy promotion mutation.
- No paper outcome mutation.
- No performance mutation.
- No AGENTS.md change.
- Do not commit.
- Do not merge.
- Do not tag.

ALLOWED:
- Public readonly Binance refresh through R262B.
- Local signed request regeneration through R262B.
- Runtime lane arming through R263 exact arming phrase.
- R264 dry preview record.
- JIT launch packet ledger.
- API/UI JIT launch card.
- Final command text generation.
- Tests with fake clients.
- Docs.

EXACT JIT PREP CONFIRMATION PHRASE:
I CONFIRM TINY LIVE JIT LAUNCH PREP ONLY; REFRESH CONTRACT-FIT TRIPLET, ARM R263 EXPERIMENTAL LANE, RUN R264 DRY PREVIEW; NO SUBMIT; NO ORDER; NO BINANCE ORDER CALL.

EXACT R263 ARMING PHRASE TO USE INTERNALLY:
I CONFIRM ARM TINY LIVE CONTROLS FOR BTCUSDT 8M SHORT EXPERIMENTAL LANE ONLY; I ACCEPT 8M SHORT IS PAPER-ONLY/PROMOTION-MISMATCHED; NO SUBMIT; NO ORDER; NO BINANCE CALL.

EXACT R264 DRY PREVIEW PHRASE TO USE INTERNALLY:
I CONFIRM TINY LIVE R264 ACTUAL SUBMIT DRY PREVIEW ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL.

FINAL LIVE SUBMIT PHRASE TO PRINT ONLY, NEVER RUN:
I CONFIRM TINY LIVE BTCUSDT 8M SHORT ACTUAL SUBMIT; USE LATEST R262B CONTRACT-FIT SIGNED TRIPLET ONLY; MAIN SELL MARKET 0.006 BTC; STOP BUY STOP_MARKET REDUCE_ONLY; TAKE_PROFIT BUY TAKE_PROFIT_MARKET REDUCE_ONLY; NO OTHER ORDERS.

CAPABILITY SCAN FIRST:
Inspect:
- src/app/hammer_radar/operator/tiny_live_percentage_risk_contract_fit_regeneration.py
- src/app/hammer_radar/operator/tiny_live_final_console.py
- src/app/hammer_radar/operator/tiny_live_actual_submit_reconciliation.py
- src/app/hammer_radar/operator/tiny_live_controls_arming.py
- src/app/hammer_radar/operator/approval_api.py
- src/app/hammer_radar/operator/inspect.py
- src/app/hammer_radar/operator/*submit* files
- src/app/hammer_radar/operator/*reconcile* files
- src/app/hammer_radar/operator/*launch* files if present
- src/app/hammer_radar/operator/*risk* files
- src/app/hammer_radar/operator/*lane* files
- src/app/hammer_radar/operator/*readiness* files
- src/app/hammer_radar/operator/*promotion* files

Inspect configs:
- configs/hammer_radar/tiny_live_risk_contracts.json
- configs/hammer_radar/lane_controls.json

Inspect ledgers:
- logs/hammer_radar_forward/tiny_live_percentage_risk_contract_fit.ndjson
- logs/hammer_radar_forward/tiny_live_final_console.ndjson
- logs/hammer_radar_forward/tiny_live_actual_submit_reconciliation.ndjson
- logs/hammer_radar_forward/tiny_live_signed_request_write_gate.ndjson
- logs/hammer_radar_forward/tiny_live_executable_payload_write_gate.ndjson

REUSE / EXTEND:
Reuse:
- R262B builder for fresh contract-fit regeneration.
- R263 final console arming builder.
- R264 actual submit dry preview builder.
- Existing lane-controls runtime arming logic.
- Existing safety object conventions.
- Existing ledger helpers.
- Existing approval_api patterns.

Do not duplicate entire child gate logic.
Orchestrate existing gates.

REQUIRED MODULE:
Create:
src/app/hammer_radar/operator/tiny_live_jit_launch_packet.py

Expose:
- build_tiny_live_jit_launch_packet
- run_r262b_contract_fit_refresh_step
- run_r263_runtime_arming_step
- run_r264_dry_preview_step
- validate_jit_launch_packet
- build_final_live_submit_command_packet
- append_tiny_live_jit_launch_packet_record
- load_tiny_live_jit_launch_packet_records
- classify_tiny_live_jit_launch_packet_status

CLI:
Wire into inspect.py as:
tiny-live-jit-launch-packet

Args:
- --run-jit-launch-prep
- --record-jit-launch-packet
- --confirm-jit-launch-prep <phrase>
- --operator-id <id> optional default local_operator
- --reason <text> optional

Preview:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-jit-launch-packet

Run JIT prep, still no submit:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-jit-launch-packet \
  --run-jit-launch-prep \
  --record-jit-launch-packet \
  --confirm-jit-launch-prep "I CONFIRM TINY LIVE JIT LAUNCH PREP ONLY; REFRESH CONTRACT-FIT TRIPLET, ARM R263 EXPERIMENTAL LANE, RUN R264 DRY PREVIEW; NO SUBMIT; NO ORDER; NO BINANCE ORDER CALL." \
  --operator-id local_operator \
  --reason "Final JIT prep for first tiny-live BTCUSDT 8m short experimental lane."

Rejected:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-jit-launch-packet \
  --run-jit-launch-prep \
  --record-jit-launch-packet \
  --confirm-jit-launch-prep "wrong"

STATUS ENUM:
- TINY_LIVE_JIT_LAUNCH_PACKET_READY
- TINY_LIVE_JIT_LAUNCH_PACKET_RECORDED
- TINY_LIVE_JIT_LAUNCH_PACKET_REJECTED
- TINY_LIVE_JIT_LAUNCH_PACKET_BLOCKED
- TINY_LIVE_JIT_LAUNCH_PACKET_ERROR

OVERALL STATUS ENUM:
- TINY_LIVE_JIT_READY_FOR_CONFIRMATION
- TINY_LIVE_JIT_RECORDED_READY_FOR_MANUAL_LIVE_COMMAND
- TINY_LIVE_JIT_REJECTED_BAD_CONFIRMATION
- TINY_LIVE_JIT_BLOCKED_BY_R262B
- TINY_LIVE_JIT_BLOCKED_BY_R263_ARMING
- TINY_LIVE_JIT_BLOCKED_BY_R264_DRY_PREVIEW
- TINY_LIVE_JIT_BLOCKED_BY_IDEMPOTENCY
- UNKNOWN_NEEDS_MANUAL_REVIEW

OUTPUT MUST INCLUDE:
{
  "status": "...",
  "generated_at": "...",
  "run_jit_launch_prep_requested": false,
  "record_jit_launch_packet_requested": false,
  "confirmation_valid": false,
  "jit_launch_packet_recorded": false,
  "target_scope": {
    "official_lane_key": "BTCUSDT|8m|short|ladder_close_50_618",
    "symbol": "BTCUSDT",
    "timeframe": "8m",
    "direction": "short",
    "jit_launch_packet_only": true,
    "submit_allowed": false,
    "order_placed": false,
    "binance_order_endpoint_called": false
  },
  "jit_step_results": {
    "r262b_contract_fit_refresh": {
      "attempted": true/false,
      "succeeded": true/false,
      "risk_contract_valid": true/false,
      "signed_triplet_fresh": true/false,
      "candidate_qty": null,
      "candidate_notional_usdt": null,
      "blocked_by": []
    },
    "r263_runtime_arming": {
      "attempted": true/false,
      "succeeded": true/false,
      "controls_armed": true/false,
      "experimental_lane_acceptance_recorded": true/false,
      "lane_controls_written": true/false,
      "blocked_by": []
    },
    "r264_dry_preview": {
      "attempted": true/false,
      "succeeded": true/false,
      "actual_submit_preview_recorded": true/false,
      "pre_submit_valid": true/false,
      "idempotency_clean": true/false,
      "blocked_by": []
    }
  },
  "jit_validation": {
    "valid": true/false,
    "blocked_by": [],
    "r262b_valid": true/false,
    "r263_armed": true/false,
    "r264_dry_preview_valid": true/false,
    "signed_triplet_fresh": true/false,
    "risk_contract_valid": true/false,
    "idempotency_clean": true/false,
    "exact_three_orders": true/false,
    "no_live_submit_performed": true
  },
  "final_live_submit_command_packet": {
    "available": true/false,
    "must_be_run_manually_by_operator": true,
    "do_not_run_from_codex": true,
    "command": "...",
    "confirmation_phrase": "...",
    "expected_orders": {
      "main": "SELL MARKET 0.006 BTC",
      "stop": "BUY STOP_MARKET REDUCE_ONLY",
      "take_profit": "BUY TAKE_PROFIT_MARKET REDUCE_ONLY"
    }
  },
  "jit_go_no_go_packet": {
    "go_for_manual_live_submit_command": true/false,
    "operator_should_submit_now": false,
    "next_required_step": "MANUAL_LIVE_COMMAND|RERUN_JIT|FIX_BLOCKER|WAIT"
  },
  "jit_launch_matrix": {
    "fresh_contract_fit_ready": true/false,
    "controls_armed": true/false,
    "dry_preview_clean": true/false,
    "manual_command_available": true/false,
    "submit_allowed": false,
    "order_placed": false,
    "blocked_by": []
  },
  "jit_launch_overall_status": "...",
  "recommended_next_operator_move": "...",
  "recommended_next_engineering_move": "...",
  "do_not_run_yet": [
    "manual live command if JIT packet is not GO",
    "manual live command twice",
    "manual live command with stale signed triplet",
    "manual live command without R263 runtime arming"
  ],
  "safety": {...}
}

SAFETY OBJECT MUST INCLUDE:
- env_written=false
- env_mutated=false
- external_env_file_written=false
- risk_contract_config_written=true only if R262B refresh updates percentage contract safely
- lane_controls_written=true only if R263 runtime arming is executed
- live_config_written=false unless existing lane_controls schema treats it as scoped live config
- jit_launch_packet_only=true
- hmac_signature_created=true only if R262B regeneration is run
- signed_request_written=true only if R262B regeneration is run
- signed_order_request_created=true only if R262B regeneration is run
- signed_trading_request_created=true only if R262B regeneration is run
- submit_allowed=false
- submit_attempted=false
- order_placed=false
- real_order_placed=false
- execution_attempted=false
- binance_order_endpoint_called=false
- binance_test_order_endpoint_called=false
- binance_account_endpoint_called=false
- binance_exchange_info_endpoint_called=true only if R262B public refresh runs
- binance_mark_price_endpoint_called=true only if R262B public refresh runs
- private_binance_endpoint_called=false
- signed_binance_endpoint_called=false
- network_allowed=true only for public readonly refresh
- transfer_endpoint_called=false
- withdraw_endpoint_called=false
- kill_switch_disabled=false
- live_controls_armed_by_phase=true only if R263 runtime arming runs
- secrets_read=false
- secrets_shown=false
- secrets_persisted=false
- secret_values_in_output=false
- global_live_flags_changed=false
- paper_live_separation_intact=true
- official_tiny_live_lane_changed=false

LEDGER:
logs/hammer_radar_forward/tiny_live_jit_launch_packet.ndjson

API/UI:
Add endpoints:
- GET /tiny-live/jit-launch-packet
- POST /tiny-live/jit-launch-packet/run

UI:
Add Tiny Live JIT Launch Packet card.
Show:
- R262B fresh status
- R263 runtime arming status
- R264 dry preview status
- manual live command packet
- giant warning: no submit from this screen
- exact command text for manual operator copy only

DOCS:
Create:
docs/hammer_radar/live_readiness/R264B_TINY_LIVE_JIT_LAUNCH_PACKET.md

Update:
docs/hammer_radar/live_readiness/R264_TINY_LIVE_ACTUAL_SUBMIT_AND_IMMEDIATE_RECONCILIATION.md
docs/hammer_radar/live_readiness/R263_TINY_LIVE_FINAL_CONSOLE_LANE_INTELLIGENCE_CONTROLS_ARMING.md
docs/hammer_radar/live_readiness/TINY_LIVE_REAL_SUBMIT_OPERATOR_RUNBOOK.md
docs/hammer_radar/live_readiness/PHASE_INDEX.md

TESTS:
Create:
tests/hammer_radar/test_tiny_live_jit_launch_packet.py

Tests must cover:
- CLI preview returns JSON and does not mutate
- wrong confirmation rejects
- exact confirmation orchestrates R262B/R263/R264 using monkeypatched child gates
- successful JIT packet emits final manual command
- no Binance order/private/account endpoint calls
- no actual submit
- no order placed
- stale signed triplet after R262B blocks
- failed R263 arming blocks
- failed R264 dry preview blocks
- idempotency dirty blocks
- secrets not in output
- API endpoint returns JSON
- UI card has no auto-submit button

VALIDATION:
Run py_compile:
- src/app/hammer_radar/operator/tiny_live_jit_launch_packet.py
- src/app/hammer_radar/operator/tiny_live_actual_submit_reconciliation.py
- src/app/hammer_radar/operator/tiny_live_final_console.py
- src/app/hammer_radar/operator/approval_api.py
- src/app/hammer_radar/operator/inspect.py

Run focused:
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar/test_tiny_live_jit_launch_packet.py

Run related:
PYTHONPATH=. .venv/bin/python -m pytest -q \
  tests/hammer_radar/test_tiny_live_actual_submit_reconciliation.py \
  tests/hammer_radar/test_tiny_live_final_console.py \
  tests/hammer_radar/test_tiny_live_percentage_risk_contract_fit_regeneration.py \
  tests/hammer_radar/test_tiny_live_controls_arming.py

Run full:
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar

SMOKE:
Preview:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-jit-launch-packet \
  | jq '.status, .target_scope, .jit_step_results, .jit_validation, .final_live_submit_command_packet, .jit_go_no_go_packet, .jit_launch_matrix, .jit_launch_overall_status, .recommended_next_operator_move, .recommended_next_engineering_move, .do_not_run_yet, .safety'

Run JIT prep:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-jit-launch-packet \
  --run-jit-launch-prep \
  --record-jit-launch-packet \
  --confirm-jit-launch-prep "I CONFIRM TINY LIVE JIT LAUNCH PREP ONLY; REFRESH CONTRACT-FIT TRIPLET, ARM R263 EXPERIMENTAL LANE, RUN R264 DRY PREVIEW; NO SUBMIT; NO ORDER; NO BINANCE ORDER CALL." \
  --operator-id local_operator \
  --reason "Final JIT prep for first tiny-live BTCUSDT 8m short experimental lane." \
  | jq '.status, .jit_launch_packet_recorded, .jit_step_results, .jit_validation, .final_live_submit_command_packet, .jit_go_no_go_packet, .jit_launch_matrix, .jit_launch_overall_status, .safety'

Rejected:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-jit-launch-packet \
  --run-jit-launch-prep \
  --record-jit-launch-packet \
  --confirm-jit-launch-prep "wrong" \
  | jq '.status, .confirmation_valid, .jit_launch_packet_recorded, .safety'

Secret leak check:
PYTHONPATH=. .venv/bin/python - <<'PY'
import os
from pathlib import Path

paths = [
    Path("logs/hammer_radar_forward/tiny_live_jit_launch_packet.ndjson"),
    Path("logs/hammer_radar_forward/tiny_live_actual_submit_reconciliation.ndjson"),
    Path("logs/hammer_radar_forward/tiny_live_percentage_risk_contract_fit.ndjson"),
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
git diff -- logs/hammer_radar_forward/paper_outcomes.ndjson || true
git diff -- logs/hammer_radar_forward/strategy_performance.ndjson || true
git diff -- logs/hammer_radar_forward/strategy_promotion_status.ndjson || true

Expected artifacts:
git status --short configs/hammer_radar/lane_controls.json || true
git status --short configs/hammer_radar/tiny_live_risk_contracts.json || true
git status --short logs/hammer_radar_forward/tiny_live_jit_launch_packet.ndjson || true
git status --short logs/hammer_radar_forward/tiny_live_actual_submit_reconciliation.ndjson || true
git status --short logs/hammer_radar_forward/tiny_live_percentage_risk_contract_fit.ndjson || true

tail -n 5 logs/hammer_radar_forward/tiny_live_jit_launch_packet.ndjson 2>/dev/null || true

FINAL PHASE REPORT REQUIRED:
At the end, report:
- phase status
- files changed
- tests run
- smoke status
- safety status
- jit_step_results
- jit_validation
- final_live_submit_command_packet
- jit_go_no_go_packet
- jit_launch_matrix
- jit_launch_overall_status
- exact files mutated
- recommended next operator move
- recommended next engineering move
- do not commit
- do not run real submit

Aggressive mode:
Complete in one pass.
This is the final launch prep compression.
No real submit.
No Binance order endpoint.
No order placement.
Do not hesitate, but do not bypass gates.
