You are in repo:
/home/josue/workspace/kernel/ai-agent-orchestrator-main

Follow:
- AGENTS.md
- codex_tasks/CODEX_RULES.md
- docs/hammer_radar/live_readiness/PHASE_INDEX.md
- docs/hammer_radar/live_readiness/TINY_LIVE_REAL_SUBMIT_OPERATOR_RUNBOOK.md
- docs/hammer_radar/live_readiness/R262B_TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_TRIPLET.md
- docs/hammer_radar/live_readiness/R262A_TINY_LIVE_RISK_CONTRACT_FIX_CONTROLS_RECHECK.md
- docs/hammer_radar/live_readiness/R261_TINY_LIVE_CONTROLS_ARMING_UI_AND_API.md
- docs/hammer_radar/live_readiness/R260_TINY_LIVE_FRESH_CYCLE_ONE_SHOT_ORCHESTRATOR.md

PHASE:
R263 Tiny-Live Final Console, Lane/Fisherman Intelligence, and Controls Arming

BRANCH:
r263-tiny-live-final-console-lane-intelligence-controls-arming

PHASE CLASSIFICATION:
Primary: FINAL PRE-SUBMIT CONSOLE / OPERATOR COCKPIT
Secondary: LANE INTELLIGENCE, FISHERMAN/PROMOTION CONTEXT, CONTROLLED ARMING, NO-SUBMIT
Duplicate risk: EXTREME

WHY THIS PHASE EXISTS:
R262B Tiny-Live Percentage Risk Contract and Contract-Fit Triplet Regeneration has been committed.

R262B fixed the immediate risk blocker:
- isolated_risk_wallet_usdt=88
- position_margin_pct_of_wallet=0.5
- resolved_position_margin_usdt=44
- leverage=10
- resolved_max_notional_usdt=440
- wallet_buffer_usdt=44
- full_wallet_is_not_position_margin=true
- risk_contract_valid_after=true
- candidate_qty=0.006 BTC
- candidate_notional_usdt approximately 384-386 USDT
- candidate_margin_usdt approximately 38.4 USDT
- candidate_estimated_loss_usdt=4.44
- fits_max_notional=true
- fits_max_loss=true
- fits_binance_step_size=true
- fits_binance_min_notional=true
- fresh_signed_request_available=true
- signed_request_fresh_enough_for_dry_preview=true
- go_for_controls_arming=true
- go_for_r263_final_console=true
- operator_should_submit_now=false

R262B did NOT:
- submit
- arm controls
- place orders
- call Binance order endpoints

Additional operator/fisherman context:
The operator inspected:
- /strategy-promotion/status
- /readiness
- /paper-executions
- local performance/promotion/paper/fisherman files

Important observed context:
- /strategy-performance endpoint returned Not Found.
- strategy promotion has promotion-ready lanes:
  - BTCUSDT|13m|long|ladder_close_50_618
    samples=268
    win_rate_pct=47.39
    avg_pnl_pct=0.0043
    total_pnl_pct=1.154
  - BTCUSDT|44m|long|ladder_close_50_618
    samples=69
    win_rate_pct=59.42
    avg_pnl_pct=0.0429
    total_pnl_pct=2.9622
- promotion config:
  - allowed_tiny_live_timeframes: 13m, 44m
  - paper_only_timeframes: 4m, 8m, 88m
  - context_only_timeframes: 4H, 13H, 13D, 888m
  - blocked_timeframes: 22m, 55m, 222m, 444m
- readiness_status=NOT_READY
- blockers:
  - no fresh ELIGIBLE_TINY_LIVE BTCUSDT candidate
  - only expired otherwise-eligible candidates are available
- latest candidate age around 20.66 minutes at inspection time
- current execution lane remains:
  BTCUSDT|8m|short|ladder_close_50_618
- Therefore current lane is paper-only / manual experimental, not promotion-ready tiny-live by default.

R263 must build the final console that shows all of this in one place and allows arming only if the operator explicitly accepts this lane context.

R263 must NOT submit.
R263 must NOT call Binance order endpoint.
R263 must NOT place orders.
R263 may arm controls only through exact confirmation and only if:
- R262B contract-fit state is valid
- risk contract is valid
- no submit occurs
- operator explicitly accepts that the current 8m short lane is paper-only/manual experimental unless switching lane is later implemented

CORE DECISION:
R263 is a final console and controls arming phase.
Actual submit is deferred to R264.

OFFICIAL EXECUTION LANE FOR THIS PHASE:
BTCUSDT|8m|short|ladder_close_50_618

PROMOTED LANES TO DISPLAY:
- BTCUSDT|13m|long|ladder_close_50_618
- BTCUSDT|44m|long|ladder_close_50_618

LANE WARNING:
The execution lane is not currently one of the promotion-ready tiny-live lanes.
The console must display this clearly.
The operator may still explicitly accept the 8m short lane as a manual experimental tiny-live lane, but this must be recorded and must not imply the fisherman promoted it.

NON-NEGOTIABLES:
- No actual submit.
- No Binance order endpoint.
- No Binance test order endpoint.
- No Binance account/private endpoint.
- No signed Binance endpoint.
- No order placement.
- No HMAC signing.
- No signed request regeneration.
- No public Binance refresh.
- No strategy promotion mutation.
- No paper outcome mutation.
- No performance mutation.
- No risk contract loosening.
- No .env write.
- No external env write.
- No secrets printed.
- No secrets persisted.
- No submit_allowed=true.
- No order endpoint readiness claim.
- No live order claim.
- No automatic lane switch to promoted lanes.
- No sudo.
- Do not commit.
- Do not merge.
- Do not tag.
- Do not touch or stage AGENTS.md.

ALLOWED:
- Read local configs and ledgers.
- Read local promotion/readiness files or call local in-process helpers.
- Add CLI final console.
- Add API/UI final console card.
- Append R263 final console ledger.
- Mutate lane_controls.json only if exact controls arming confirmation is provided.
- Record operator acceptance of experimental lane context.
- Create R264 actual submit task.

EXACT FINAL CONSOLE REVIEW CONFIRMATION PHRASE:
I CONFIRM TINY LIVE FINAL CONSOLE REVIEW RECORDING ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL.

EXACT CONTROLS ARMING CONFIRMATION PHRASE:
I CONFIRM ARM TINY LIVE CONTROLS FOR BTCUSDT 8M SHORT EXPERIMENTAL LANE ONLY; I ACCEPT 8M SHORT IS PAPER-ONLY/PROMOTION-MISMATCHED; NO SUBMIT; NO ORDER; NO BINANCE CALL.

IMPORTANT:
Do not reuse the old R261 arming phrase blindly if it does not capture experimental lane acceptance.
R263 must require the new stronger phrase for arming because lane intelligence says 8m short is not promotion-ready by default.

CAPABILITY SCAN FIRST:
Inspect:
- src/app/hammer_radar/operator/tiny_live_percentage_risk_contract_fit_regeneration.py
- src/app/hammer_radar/operator/tiny_live_controls_arming.py
- src/app/hammer_radar/operator/tiny_live_risk_contract_fix.py
- src/app/hammer_radar/operator/tiny_live_fresh_cycle_one_shot_orchestrator.py
- src/app/hammer_radar/operator/tiny_live_actual_submit_gate.py
- src/app/hammer_radar/operator/tiny_live_submit_gate_preview.py
- src/app/hammer_radar/operator/approval_api.py
- src/app/hammer_radar/operator/inspect.py
- src/app/hammer_radar/operator/*promotion* files
- src/app/hammer_radar/operator/*readiness* files
- src/app/hammer_radar/operator/*fisher* files
- src/app/hammer_radar/operator/*lane* files
- src/app/hammer_radar/operator/*score* files
- src/app/hammer_radar/operator/*performance* files
- src/app/hammer_radar/operator/*submit* files
- src/app/hammer_radar/operator/*controls* files
- src/app/hammer_radar/operator/*api* files
- src/app/hammer_radar/operator/*dashboard* files

Inspect configs:
- configs/hammer_radar/tiny_live_risk_contracts.json
- configs/hammer_radar/lane_controls.json
- configs/hammer_radar/*.json

Inspect ledgers:
- logs/hammer_radar_forward/tiny_live_percentage_risk_contract_fit.ndjson
- logs/hammer_radar_forward/tiny_live_controls_arming.ndjson
- logs/hammer_radar_forward/tiny_live_actual_submit_gate.ndjson
- logs/hammer_radar_forward/tiny_live_submit_gate_preview.ndjson
- logs/hammer_radar_forward/tiny_live_fresh_context_signed_request_regeneration_gate.ndjson
- logs/hammer_radar_forward/tiny_live_signed_request_write_gate.ndjson
- logs/hammer_radar_forward/tiny_live_executable_payload_write_gate.ndjson
- logs/hammer_radar_forward/tiny_live_stop_take_profit_source_gate.ndjson
- logs/hammer_radar_forward/strategy_promotion_events.ndjson
- logs/hammer_radar_forward/full_spectrum_lane_scoreboard.ndjson
- logs/hammer_radar_forward/fisherman_watchdog_ledger_reconciliation.ndjson
- logs/hammer_radar_forward/paper_executions.ndjson
- logs/hammer_radar_forward/outcomes.ndjson
- logs/hammer_radar_forward/betrayal_*.ndjson if relevant and safe to summarize read-only

Inspect docs:
- docs/hammer_radar/live_readiness/R262B_TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_TRIPLET.md
- docs/hammer_radar/live_readiness/R262A_TINY_LIVE_RISK_CONTRACT_FIX_CONTROLS_RECHECK.md
- docs/hammer_radar/live_readiness/R261_TINY_LIVE_CONTROLS_ARMING_UI_AND_API.md
- docs/hammer_radar/live_readiness/TINY_LIVE_REAL_SUBMIT_OPERATOR_RUNBOOK.md
- docs/hammer_radar/live_readiness/PHASE_INDEX.md

Inspect tests:
- tests/hammer_radar/test_tiny_live_percentage_risk_contract_fit_regeneration.py
- tests/hammer_radar/test_tiny_live_controls_arming.py
- tests/hammer_radar/test_tiny_live_risk_contract_fix.py
- tests/hammer_radar/test_tiny_live_actual_submit_gate.py
- tests/hammer_radar/test_*promotion* if present
- tests/hammer_radar/test_*readiness* if present
- tests/hammer_radar/test_*fisher* if present
- tests/hammer_radar/test_*lane* if present
- tests/hammer_radar/test_*api* if present
- tests/hammer_radar/test_*dashboard* if present

REUSE / EXTEND:
Reuse:
- R262B latest ledger loader
- R261 controls arming state helpers
- R261 API/UI conventions
- existing approval_api dashboard HTML if present
- existing lane_controls writer if safe
- existing promotion/readiness builders if present
- existing safety object conventions
- existing NDJSON append helper

Do not duplicate large logic if importable.
Do not bypass R262B/R261.
Do not implement submit here.

REQUIRED MODULE:
Create:
src/app/hammer_radar/operator/tiny_live_final_console.py

Expose:
- build_tiny_live_final_console
- load_latest_percentage_contract_fit_record
- load_latest_controls_arming_record
- load_tiny_live_lane_controls
- load_strategy_promotion_status_snapshot
- load_readiness_snapshot
- load_lane_fisherman_context
- summarize_contract_fit_panel
- summarize_signed_triplet_panel
- summarize_controls_panel
- summarize_lane_intelligence_panel
- summarize_promotion_readiness_panel
- build_operator_choice_panel
- validate_final_console_controls_arming_request
- apply_final_console_controls_arming_request
- build_final_console_go_no_go_packet
- append_tiny_live_final_console_record
- load_tiny_live_final_console_records
- classify_tiny_live_final_console_status

CLI:
Wire into inspect.py as:
tiny-live-final-console

Args:
- --record-final-console-review
- --confirm-final-console-review <phrase>
- --arm-controls-from-final-console
- --confirm-final-console-controls-arming <phrase>
- --operator-id <id> optional default local_operator
- --reason <text> optional

Preview:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-final-console

Record review:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-final-console \
  --record-final-console-review \
  --confirm-final-console-review "I CONFIRM TINY LIVE FINAL CONSOLE REVIEW RECORDING ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL."

Arm controls from console:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-final-console \
  --arm-controls-from-final-console \
  --confirm-final-console-controls-arming "I CONFIRM ARM TINY LIVE CONTROLS FOR BTCUSDT 8M SHORT EXPERIMENTAL LANE ONLY; I ACCEPT 8M SHORT IS PAPER-ONLY/PROMOTION-MISMATCHED; NO SUBMIT; NO ORDER; NO BINANCE CALL." \
  --operator-id local_operator \
  --reason "R263 final console accepted contract-fit 8m short experimental lane; preparing for R264 actual submit checkpoint."

Rejected:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-final-console \
  --arm-controls-from-final-console \
  --confirm-final-console-controls-arming "wrong"

STATUS ENUM:
- TINY_LIVE_FINAL_CONSOLE_READY
- TINY_LIVE_FINAL_CONSOLE_REVIEW_RECORDED
- TINY_LIVE_FINAL_CONSOLE_CONTROLS_ARMED
- TINY_LIVE_FINAL_CONSOLE_ARMING_REJECTED
- TINY_LIVE_FINAL_CONSOLE_BLOCKED
- TINY_LIVE_FINAL_CONSOLE_ERROR

OVERALL STATUS ENUM:
- TINY_LIVE_FINAL_CONSOLE_READY_FOR_REVIEW
- TINY_LIVE_FINAL_CONSOLE_REVIEW_RECORDED_ARMING_REQUIRED
- TINY_LIVE_FINAL_CONSOLE_ARMED_R264_ACTUAL_SUBMIT_CHECKPOINT_REQUIRED
- TINY_LIVE_FINAL_CONSOLE_BLOCKED_BY_MISSING_R262B
- TINY_LIVE_FINAL_CONSOLE_BLOCKED_BY_CONTRACT_INVALID
- TINY_LIVE_FINAL_CONSOLE_BLOCKED_BY_LANE_INTELLIGENCE
- TINY_LIVE_FINAL_CONSOLE_ARMING_REJECTED_BAD_CONFIRMATION
- UNKNOWN_NEEDS_MANUAL_REVIEW

OUTPUT MUST INCLUDE:
{
  "status": "...",
  "generated_at": "...",
  "record_final_console_review_requested": false,
  "arm_controls_from_final_console_requested": false,
  "confirmation_valid": false,
  "final_console_review_recorded": false,
  "final_console_controls_armed": false,
  "target_scope": {
    "official_lane_key": "BTCUSDT|8m|short|ladder_close_50_618",
    "symbol": "BTCUSDT",
    "timeframe": "8m",
    "direction": "short",
    "final_console_only": true,
    "submit_allowed": false,
    "order_placed": false,
    "binance_order_endpoint_called": false
  },
  "contract_fit_panel": {
    "r262b_found": true/false,
    "risk_contract_valid": true/false,
    "percentage_model_ready": true/false,
    "isolated_risk_wallet_usdt": 88,
    "position_margin_usdt": 44,
    "wallet_buffer_usdt": 44,
    "leverage": 10,
    "candidate_qty": null,
    "candidate_notional_usdt": null,
    "candidate_margin_usdt": null,
    "candidate_estimated_loss_usdt": null,
    "fits_contract": true/false
  },
  "signed_triplet_panel": {
    "signed_triplet_available": true/false,
    "signed_requests_count": null,
    "main_order_side": "SELL",
    "stop_reduce_only": true/false,
    "take_profit_reduce_only": true/false,
    "submit_preview_recorded": true/false,
    "dry_preview_recorded": true/false,
    "dry_preview_risk_contract_valid": true/false
  },
  "controls_panel": {
    "official_lane_allowed": true/false,
    "live_execution_enabled": true/false,
    "kill_switch_allows_tiny_live": true/false,
    "controls_armed": true/false,
    "controls_arming_required": true/false
  },
  "lane_intelligence_panel": {
    "execution_lane": "BTCUSDT|8m|short|ladder_close_50_618",
    "execution_lane_timeframe_status": "paper_only|allowed_tiny_live|blocked|unknown",
    "execution_lane_promotion_status": "not_promotion_ready|promotion_ready|unknown",
    "execution_lane_direction_status": "experimental_short|promoted|unknown",
    "promoted_lanes": [],
    "readiness_status": "READY|NOT_READY|UNKNOWN",
    "fresh_eligible_count": null,
    "expired_eligible_count": null,
    "paper_only_count": null,
    "fisherman_warning": true/false,
    "operator_acceptance_required": true/false,
    "warnings": []
  },
  "promotion_readiness_panel": {
    "strategy_performance_endpoint_available": true/false,
    "promotion_ready": [],
    "readiness_blockers": [],
    "latest_candidate_age_minutes": null,
    "live_execution_enabled": false,
    "global_kill_switch": true/false
  },
  "operator_choice_panel": {
    "choices": [
      "ACCEPT_8M_SHORT_EXPERIMENTAL_LANE",
      "WAIT_FOR_FRESH_ELIGIBLE_TINY_LIVE",
      "SWITCH_TO_PROMOTED_13M_LONG_LATER",
      "SWITCH_TO_PROMOTED_44M_LONG_LATER"
    ],
    "selected_choice": null,
    "experimental_lane_acceptance_recorded": true/false,
    "submit_still_forbidden": true
  },
  "controls_arming_result": {
    "attempted": true/false,
    "succeeded": true/false,
    "lane_controls_written": true/false,
    "blocked_by": [],
    "before": {},
    "after": {}
  },
  "final_console_go_no_go_packet": {
    "go_for_actual_submit_now": false,
    "go_for_r264_actual_submit_checkpoint": true/false,
    "go_for_controls_arming": true/false,
    "operator_should_submit_now": false,
    "next_required_step": "ARM_CONTROLS|R264_ACTUAL_SUBMIT_CHECKPOINT|WAIT_FOR_FRESH_CANDIDATE|SWITCH_LANE_LATER|RERUN_R262B|FIX_BLOCKER"
  },
  "final_console_matrix": {
    "r262b_valid": true/false,
    "signed_triplet_available": true/false,
    "risk_contract_valid": true/false,
    "lane_intelligence_loaded": true/false,
    "experimental_lane_acceptance_required": true/false,
    "experimental_lane_acceptance_recorded": true/false,
    "controls_armed": true/false,
    "submit_allowed": false,
    "order_placed": false,
    "blocked_by": []
  },
  "final_console_overall_status": "...",
  "recommended_next_operator_move": "...",
  "recommended_next_engineering_move": "...",
  "do_not_run_yet": [
    "real submit from R263",
    "real submit before R264 checkpoint",
    "real submit without controls armed",
    "real submit while lane/fisherman warning is unaccepted",
    "duplicate live submit"
  ],
  "safety": {...}
}

SAFETY OBJECT MUST INCLUDE:
- env_written=false
- env_mutated=false
- external_env_file_written=false
- risk_contract_config_written=false
- lane_controls_written=true only if exact final-console arming confirmation succeeds
- live_config_written=false unless lane_controls schema treats scoped live config as live config
- final_console_only=true
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
- live_controls_armed_by_phase=true only if exact final-console arming succeeds
- secrets_read=false
- secrets_shown=false
- secrets_persisted=false
- secret_values_in_output=false
- global_live_flags_changed=false unless existing scoped lane controls require it; document if scoped
- paper_live_separation_intact=true
- official_tiny_live_lane_changed=false
- experimental_lane_acceptance_recorded=true only if exact final-console arming succeeds

LEDGER:
logs/hammer_radar_forward/tiny_live_final_console.ndjson

CONFIG:
May update:
- configs/hammer_radar/lane_controls.json

Only when exact final-console arming confirmation succeeds.
Do not update risk contract config in R263.

API/UI:
Add endpoints to approval_api.py:
- GET /tiny-live/final-console
- POST /tiny-live/final-console/review/record
- POST /tiny-live/final-console/controls/arm

Dashboard/UI:
Add a Tiny Live Final Console panel/card.

Must display:
- R262B contract-fit panel
- signed triplet panel
- controls panel
- lane/fisherman intelligence panel
- promoted lanes
- readiness blockers
- final go/no-go packet
- explicit “NO SUBMIT FROM THIS SCREEN”
- controls arming form with exact phrase
- no actual submit button

DOCS:
Create:
docs/hammer_radar/live_readiness/R263_TINY_LIVE_FINAL_CONSOLE_LANE_INTELLIGENCE_CONTROLS_ARMING.md

Update:
docs/hammer_radar/live_readiness/R262B_TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_TRIPLET.md
docs/hammer_radar/live_readiness/R261_TINY_LIVE_CONTROLS_ARMING_UI_AND_API.md
docs/hammer_radar/live_readiness/TINY_LIVE_REAL_SUBMIT_OPERATOR_RUNBOOK.md
docs/hammer_radar/live_readiness/PHASE_INDEX.md

FUTURE TASK:
Create or update:
codex_tasks/phases/R264_TINY_LIVE_ACTUAL_SUBMIT_AND_IMMEDIATE_RECONCILIATION.md

R264 must:
- require R263 final console controls armed
- require R262B valid contract-fit triplet
- require no duplicate live submit
- require exact submit phrase
- submit exactly three orders only:
  1. main market order
  2. reduce-only stop
  3. reduce-only take profit
- immediately reconcile exchange order ids
- handle partial success
- no extra orders

TESTS:
Create:
tests/hammer_radar/test_tiny_live_final_console.py

Tests must cover:
- CLI preview returns JSON
- review record exact phrase records review only
- wrong arming phrase rejects
- exact arming phrase records experimental lane acceptance and writes only lane_controls.json
- no submit/order/Binance/signing in any R263 path
- R262B valid panel loads latest record
- 8m short lane marked paper_only/promotion-mismatched
- promoted 13m and 44m long lanes shown when promotion status fixture contains them
- readiness NOT_READY shown when no fresh eligible candidate
- final console blocks actual submit
- API GET final console returns JSON
- API POST arm requires exact phrase
- UI contains no actual submit button
- no secrets in output

VALIDATION:
Run py_compile:
- src/app/hammer_radar/operator/tiny_live_final_console.py
- src/app/hammer_radar/operator/tiny_live_controls_arming.py
- src/app/hammer_radar/operator/approval_api.py
- src/app/hammer_radar/operator/inspect.py

Run focused:
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar/test_tiny_live_final_console.py

Run related:
PYTHONPATH=. .venv/bin/python -m pytest -q \
  tests/hammer_radar/test_tiny_live_percentage_risk_contract_fit_regeneration.py \
  tests/hammer_radar/test_tiny_live_controls_arming.py \
  tests/hammer_radar/test_tiny_live_risk_contract_fix.py \
  tests/hammer_radar/test_tiny_live_actual_submit_gate.py

Run API/UI related tests if present.

Run full:
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar

SMOKE:
Preview:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-final-console \
  | jq '.status, .target_scope, .contract_fit_panel, .signed_triplet_panel, .controls_panel, .lane_intelligence_panel, .promotion_readiness_panel, .operator_choice_panel, .controls_arming_result, .final_console_go_no_go_packet, .final_console_matrix, .final_console_overall_status, .recommended_next_operator_move, .recommended_next_engineering_move, .do_not_run_yet, .safety'

Record review:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-final-console \
  --record-final-console-review \
  --confirm-final-console-review "I CONFIRM TINY LIVE FINAL CONSOLE REVIEW RECORDING ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL." \
  | jq '.status, .final_console_review_recorded, .operator_choice_panel, .final_console_go_no_go_packet, .final_console_matrix, .final_console_overall_status, .safety'

Rejected arming:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-final-console \
  --arm-controls-from-final-console \
  --confirm-final-console-controls-arming "wrong" \
  | jq '.status, .confirmation_valid, .final_console_controls_armed, .controls_arming_result, .safety'

Arm controls:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-final-console \
  --arm-controls-from-final-console \
  --confirm-final-console-controls-arming "I CONFIRM ARM TINY LIVE CONTROLS FOR BTCUSDT 8M SHORT EXPERIMENTAL LANE ONLY; I ACCEPT 8M SHORT IS PAPER-ONLY/PROMOTION-MISMATCHED; NO SUBMIT; NO ORDER; NO BINANCE CALL." \
  --operator-id local_operator \
  --reason "R263 final console accepted contract-fit 8m short experimental lane; preparing for R264 actual submit checkpoint." \
  | jq '.status, .final_console_controls_armed, .controls_panel, .operator_choice_panel, .controls_arming_result, .final_console_go_no_go_packet, .final_console_matrix, .final_console_overall_status, .safety'

Secret leak check:
PYTHONPATH=. .venv/bin/python - <<'PY'
import os
from pathlib import Path

paths = [
    Path("logs/hammer_radar_forward/tiny_live_final_console.ndjson"),
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
git diff -- logs/hammer_radar_forward/candles_BTCUSDT_8m.ndjson || true
git diff -- logs/hammer_radar_forward/paper_outcomes.ndjson || true
git diff -- logs/hammer_radar_forward/strategy_performance.ndjson || true
git diff -- logs/hammer_radar_forward/strategy_promotion_status.ndjson || true

Expected artifacts:
git status --short configs/hammer_radar/lane_controls.json || true
git status --short logs/hammer_radar_forward/tiny_live_final_console.ndjson || true

git diff -- configs/hammer_radar/lane_controls.json || true
tail -n 5 logs/hammer_radar_forward/tiny_live_final_console.ndjson 2>/dev/null || true

FINAL PHASE REPORT REQUIRED:
At the end, report:
- phase status
- files changed
- tests run
- smoke status
- safety status
- contract_fit_panel
- signed_triplet_panel
- controls_panel
- lane_intelligence_panel
- promotion_readiness_panel
- operator_choice_panel
- controls_arming_result
- final_console_go_no_go_packet
- final_console_matrix
- final_console_overall_status
- API/UI endpoints added
- exact files mutated
- recommended next operator move
- recommended next engineering move
- do not commit
- do not run real submit

Aggressive mode:
Complete in one pass.
Build the final console and lane intelligence.
Arm controls only with exact experimental-lane acceptance.
Do not submit.
Do not call Binance.
Do not sign.
Do not place orders.
No actual submit button.
