You are in repo:
/home/josue/workspace/kernel/ai-agent-orchestrator-main

Follow:
- AGENTS.md
- codex_tasks/CODEX_RULES.md
- docs/hammer_radar/live_readiness/PHASE_INDEX.md
- docs/hammer_radar/live_readiness/TINY_LIVE_REAL_SUBMIT_OPERATOR_RUNBOOK.md
- docs/hammer_radar/live_readiness/R262A_TINY_LIVE_RISK_CONTRACT_FIX_CONTROLS_RECHECK.md
- docs/hammer_radar/live_readiness/R261_TINY_LIVE_CONTROLS_ARMING_UI_AND_API.md
- docs/hammer_radar/live_readiness/R260_TINY_LIVE_FRESH_CYCLE_ONE_SHOT_ORCHESTRATOR.md

PHASE:
R262B Tiny-Live Percentage Risk Contract and Contract-Fit Triplet Regeneration

BRANCH:
r262b-tiny-live-percentage-risk-contract-fit-triplet

PHASE CLASSIFICATION:
Primary: RISK CONTRACT MODEL UPGRADE / CONTRACT-FIT SIGNED TRIPLET REGENERATION
Secondary: PERCENTAGE-BASED RISK, ISOLATED WALLET BUFFER, PRE-LIVE READINESS
Duplicate risk: EXTREME

WHY THIS PHASE EXISTS:
R262A diagnosed the real blocker:
- risk contract root cause: unsafe_limits
- current triplet notional_usdt: 451.2578
- current max_notional_usdt: 440
- current estimated_loss_usdt: 4.4401
- current max_loss_usdt: 4.44
- blocked_by: notional_exceeds_max_notional_buffer
- risk contract valid after: false
- controls armed: false

R262A correctly refused to loosen fixed limits.

The operator clarified the intended risk architecture:
- each isolated risk wallet should contain 88 USDT
- each live position should use only 44 USDT margin
- leverage should remain 10x
- position notional should remain approximately 440 USDT
- the extra 44 USDT is isolated wallet buffer, not intended position margin
- future contracts should be percentage-based, not fixed-number-only, so when account grows the same proportional model can self-perpetuate

Therefore R262B must:
1. Convert/extend the tiny-live risk contract model to a percentage-based wallet contract.
2. Resolve current values from the percentage model:
   - isolated_wallet_usdt = 88
   - position_margin_pct_of_wallet = 50%
   - resolved_position_margin_usdt = 44
   - leverage = 10
   - resolved_max_notional_usdt = 440
3. Regenerate a fresh triplet that fits the resolved contract, especially:
   - notional <= resolved_max_notional_usdt
   - estimated loss <= resolved_max_loss_usdt
   - quantity respects Binance step size/min notional
4. Avoid increasing risk.
5. Avoid changing leverage above 10.
6. Avoid live submit.
7. Avoid arming controls unless explicitly part of a review-only result, not mutation.
8. Produce a new valid R260/R255/R261-compatible state for R263 final submit console.

OFFICIAL LANE:
BTCUSDT|8m|short|ladder_close_50_618

TARGET CURRENT WALLET MODEL:
- isolated_risk_wallet_usdt: 88
- position_margin_pct_of_wallet: 0.50
- resolved_position_margin_usdt: 44
- leverage: 10
- resolved_max_notional_usdt: 440
- max_loss_pct_of_position_margin: 0.1009 approximately, but resolve from existing 4.44 / 44 if already defined
- resolved_max_loss_usdt: 4.44
- contract values should be stored as percentages where durable
- resolved values should be recorded as derived runtime values

IMPORTANT:
Do NOT “fix” this by raising max_notional above 440.
Do NOT “fix” this by raising max_loss above 4.44.
Do NOT “fix” this by raising leverage above 10.
Do NOT “fix” this by using the full 88 USDT as margin.
The 88 USDT is isolated wallet allocation.
The position margin target remains 44 USDT.

CORE INTENT:
Create a compact percentage-based risk contract + contract-fit regeneration layer that:
1. Diagnoses current fixed risk contract.
2. Adds or derives percentage fields safely.
3. Keeps current resolved risk at 44 margin / 440 notional / 4.44 max loss.
4. Rebuilds the fresh signed triplet so quantity fits under 440 notional at fresh mark.
5. Produces R254 submit preview.
6. Produces R255 dry preview.
7. Produces R261 controls review.
8. Shows risk contract valid after regeneration.
9. Does not submit.
10. Does not arm controls by default.
11. Produces R263 final submit console task update.

NON-NEGOTIABLES:
- No real submit.
- No Binance order endpoint.
- No Binance test order endpoint.
- No Binance account/private endpoint.
- No signed Binance endpoint.
- No order placement.
- No live-control arming in R262B.
- No lane_controls mutation unless docs/tests need read-only status, but prefer none.
- No .env write.
- No external env write.
- No API secret printed.
- No API key printed.
- No secret persistence.
- No leverage above 10.
- No position margin above 44 current resolved USDT.
- No max notional above 440 current resolved USDT.
- No max loss above 4.44 current resolved USDT.
- No full 88 USDT position margin.
- No weakening reduce-only exit requirements.
- No weakening exact 3-order triplet requirement.
- No weakening operator confirmation.
- No paper_outcomes append.
- No strategy performance append.
- No promotion status append.
- No sudo.
- Do not commit.
- Do not merge.
- Do not tag.
- Do not touch or stage AGENTS.md.

ALLOWED:
- Read public Binance readonly endpoints only through existing R253 logic.
- Regenerate local signed requests only through existing R253B/runtime-source signing path.
- Write the risk contract config only if converting to percentage schema without loosening resolved risk.
- Write regeneration/preview/dry/review ledgers.
- Update docs/tests.
- Update R263 future task.

EXACT CONFIRMATION PHRASE:
I CONFIRM TINY LIVE PERCENTAGE RISK CONTRACT FIT REGENERATION ONLY; 88 USDT ISOLATED WALLET, 44 USDT POSITION MARGIN, 10X LEVERAGE, KEEP RISK SAME OR STRICTER; NO SUBMIT; NO ORDER; NO BINANCE ORDER CALL.

CAPABILITY SCAN FIRST:
Inspect:
- src/app/hammer_radar/operator/tiny_live_risk_contract_fix.py
- src/app/hammer_radar/operator/tiny_live_controls_arming.py
- src/app/hammer_radar/operator/tiny_live_fresh_cycle_one_shot_orchestrator.py
- src/app/hammer_radar/operator/tiny_live_actual_submit_gate.py
- src/app/hammer_radar/operator/tiny_live_submit_gate_preview.py
- src/app/hammer_radar/operator/tiny_live_fresh_context_signed_request_regeneration_gate.py
- src/app/hammer_radar/operator/tiny_live_final_readonly_mark_price_refresh_gate.py
- src/app/hammer_radar/operator/tiny_live_signed_request_runtime_source_write_gate.py
- src/app/hammer_radar/operator/tiny_live_signed_request_write_gate.py
- src/app/hammer_radar/operator/tiny_live_executable_payload_write_gate.py
- src/app/hammer_radar/operator/tiny_live_stop_take_profit_source_gate.py
- src/app/hammer_radar/operator/inspect.py
- src/app/hammer_radar/operator/*risk* files
- src/app/hammer_radar/operator/*contract* files
- src/app/hammer_radar/operator/*sizing* files
- src/app/hammer_radar/operator/*notional* files
- src/app/hammer_radar/operator/*regeneration* files
- src/app/hammer_radar/operator/*submit* files

Inspect configs:
- configs/hammer_radar/tiny_live_risk_contracts.json
- configs/hammer_radar/lane_controls.json
- configs/hammer_radar/*.json

Inspect ledgers:
- logs/hammer_radar_forward/tiny_live_risk_contract_fix.ndjson
- logs/hammer_radar_forward/tiny_live_controls_arming.ndjson
- logs/hammer_radar_forward/tiny_live_fresh_cycle_one_shot.ndjson
- logs/hammer_radar_forward/tiny_live_actual_submit_gate.ndjson
- logs/hammer_radar_forward/tiny_live_submit_gate_preview.ndjson
- logs/hammer_radar_forward/tiny_live_fresh_context_signed_request_regeneration_gate.ndjson
- logs/hammer_radar_forward/tiny_live_final_readonly_mark_price_refresh_gate.ndjson
- logs/hammer_radar_forward/tiny_live_signed_request_write_gate.ndjson
- logs/hammer_radar_forward/tiny_live_executable_payload_write_gate.ndjson
- logs/hammer_radar_forward/tiny_live_stop_take_profit_source_gate.ndjson

Inspect docs:
- docs/hammer_radar/live_readiness/R262A_TINY_LIVE_RISK_CONTRACT_FIX_CONTROLS_RECHECK.md
- docs/hammer_radar/live_readiness/R261_TINY_LIVE_CONTROLS_ARMING_UI_AND_API.md
- docs/hammer_radar/live_readiness/R260_TINY_LIVE_FRESH_CYCLE_ONE_SHOT_ORCHESTRATOR.md
- docs/hammer_radar/live_readiness/TINY_LIVE_REAL_SUBMIT_OPERATOR_RUNBOOK.md
- docs/hammer_radar/live_readiness/PHASE_INDEX.md

Inspect tests:
- tests/hammer_radar/test_tiny_live_risk_contract_fix.py
- tests/hammer_radar/test_tiny_live_controls_arming.py
- tests/hammer_radar/test_tiny_live_fresh_cycle_one_shot_orchestrator.py
- tests/hammer_radar/test_tiny_live_actual_submit_gate.py
- tests/hammer_radar/test_tiny_live_fresh_context_signed_request_regeneration_gate.py
- tests/hammer_radar/test_*risk* if present
- tests/hammer_radar/test_*sizing* if present

REUSE / EXTEND:
Reuse:
- existing risk contract loader
- existing R262A diagnostic validator
- existing R253 readonly refresh logic
- existing R253B regeneration logic
- existing R254 preview logic
- existing R255 dry preview logic
- existing R261 controls review logic
- existing ledger helpers
- existing safety object conventions

Do not fork the pipeline.
Do not create a separate order model.
Do not bypass existing gates.

REQUIRED MODULE:
Create:
src/app/hammer_radar/operator/tiny_live_percentage_risk_contract_fit_regeneration.py

Expose:
- build_tiny_live_percentage_risk_contract_fit_regeneration
- load_current_tiny_live_risk_contract
- derive_percentage_risk_contract_model
- resolve_percentage_risk_contract_values
- validate_percentage_contract_same_or_stricter
- build_contract_fit_sizing_plan
- compute_contract_fit_quantity
- validate_quantity_fits_contract
- apply_percentage_risk_contract_schema_update
- run_contract_fit_readonly_refresh
- run_contract_fit_signed_regeneration
- run_contract_fit_submit_preview
- run_contract_fit_dry_preview
- run_contract_fit_controls_review
- build_contract_fit_output_validation
- build_contract_fit_go_no_go_packet
- append_tiny_live_percentage_contract_fit_record
- load_tiny_live_percentage_contract_fit_records
- classify_tiny_live_percentage_contract_fit_status

CLI:
Wire into inspect.py as:
tiny-live-percentage-risk-contract-fit

Args:
- --run-contract-fit-regeneration
- --record-contract-fit-regeneration
- --confirm-contract-fit-regeneration <phrase>

Preview:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-percentage-risk-contract-fit

Run:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-percentage-risk-contract-fit \
  --run-contract-fit-regeneration \
  --record-contract-fit-regeneration \
  --confirm-contract-fit-regeneration "I CONFIRM TINY LIVE PERCENTAGE RISK CONTRACT FIT REGENERATION ONLY; 88 USDT ISOLATED WALLET, 44 USDT POSITION MARGIN, 10X LEVERAGE, KEEP RISK SAME OR STRICTER; NO SUBMIT; NO ORDER; NO BINANCE ORDER CALL."

Rejected:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-percentage-risk-contract-fit \
  --run-contract-fit-regeneration \
  --record-contract-fit-regeneration \
  --confirm-contract-fit-regeneration "wrong"

STATUS ENUM:
- TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_READY
- TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_RECORDED
- TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_REJECTED
- TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_BLOCKED
- TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_ERROR

OVERALL STATUS ENUM:
- TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_READY_FOR_CONFIRMATION
- TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_RECORDED_CONTROLS_REVIEW_REQUIRED
- TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_RECORDED_RISK_VALID
- TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_REJECTED_BAD_CONFIRMATION
- TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_BLOCKED_UNSAFE_RISK_CHANGE
- TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_BLOCKED_BY_SIZING
- UNKNOWN_NEEDS_MANUAL_REVIEW

OUTPUT MUST INCLUDE:
{
  "status": "...",
  "generated_at": "...",
  "run_contract_fit_regeneration_requested": false,
  "record_contract_fit_regeneration_requested": false,
  "confirmation_valid": false,
  "contract_fit_regeneration_recorded": false,
  "target_scope": {
    "official_lane_key": "BTCUSDT|8m|short|ladder_close_50_618",
    "symbol": "BTCUSDT",
    "timeframe": "8m",
    "direction": "short",
    "percentage_risk_contract_fit_only": true,
    "submit_allowed": false,
    "order_placed": false,
    "binance_order_endpoint_called": false
  },
  "operator_intervention_model": {
    "isolated_risk_wallet_usdt": 88,
    "position_margin_pct_of_wallet": 0.5,
    "resolved_position_margin_usdt": 44,
    "leverage": 10,
    "resolved_max_notional_usdt": 440,
    "wallet_buffer_usdt": 44,
    "wallet_buffer_pct_of_wallet": 0.5,
    "full_wallet_is_not_position_margin": true
  },
  "percentage_contract_model": {
    "uses_percentage_model": true,
    "isolated_wallet_reference_pct": 1.0,
    "position_margin_pct_of_isolated_wallet": 0.5,
    "max_notional_multiplier_of_position_margin": 10,
    "max_loss_pct_of_position_margin": null,
    "resolved_values": {}
  },
  "contract_fit_sizing_plan": {
    "fresh_mark_price": null,
    "max_notional_usdt": 440,
    "candidate_qty": null,
    "candidate_notional_usdt": null,
    "candidate_margin_usdt": null,
    "candidate_estimated_loss_usdt": null,
    "fits_max_notional": true/false,
    "fits_max_loss": true/false,
    "fits_binance_step_size": true/false,
    "fits_binance_min_notional": true/false,
    "blocked_by": []
  },
  "step_results": {
    "percentage_schema_update": {
      "attempted": true/false,
      "succeeded": true/false,
      "risk_contract_config_written": true/false,
      "blocked_by": []
    },
    "readonly_refresh": {
      "attempted": true/false,
      "succeeded": true/false,
      "fresh_mark_price": null,
      "blocked_by": []
    },
    "signed_regeneration": {
      "attempted": true/false,
      "succeeded": true/false,
      "signed_requests_count": null,
      "blocked_by": []
    },
    "submit_preview": {
      "attempted": true/false,
      "succeeded": true/false,
      "blocked_by": []
    },
    "dry_preview": {
      "attempted": true/false,
      "succeeded": true/false,
      "risk_contract_valid": true/false,
      "blocked_by": []
    },
    "controls_review": {
      "attempted": true/false,
      "succeeded": true/false,
      "operator_should_arm_controls": true/false,
      "blocked_by": []
    }
  },
  "output_validation": {
    "valid": true/false,
    "risk_contract_valid_after": true/false,
    "fresh_signed_request_available": true/false,
    "signed_request_fresh_enough_for_dry_preview": true/false,
    "notional_within_contract": true/false,
    "loss_within_contract": true/false,
    "no_risk_limit_increase": true/false,
    "errors": [],
    "warnings": []
  },
  "go_no_go_packet": {
    "go_for_manual_submit_now": false,
    "go_for_controls_arming": true/false,
    "go_for_r263_final_console": true/false,
    "next_required_step": "ARM_CONTROLS|R263_FINAL_CONSOLE|RERUN_CONTRACT_FIT|FIX_BLOCKER|WAIT",
    "operator_should_submit_now": false
  },
  "contract_fit_matrix": {
    "percentage_model_ready": true/false,
    "sizing_fit_ready": true/false,
    "risk_contract_valid": true/false,
    "fresh_cycle_valid": true/false,
    "controls_review_ready": true/false,
    "submit_allowed": false,
    "order_placed": false,
    "blocked_by": []
  },
  "contract_fit_overall_status": "...",
  "recommended_next_operator_move": "...",
  "recommended_next_engineering_move": "...",
  "do_not_run_yet": [
    "real submit from R262B",
    "real submit before controls arming",
    "real submit before final console",
    "duplicate live submit"
  ],
  "safety": {...}
}

SAFETY OBJECT MUST INCLUDE:
- env_written=false
- env_mutated=false
- external_env_file_written=false
- risk_contract_config_written=true only if percentage schema update occurs with same/stricter resolved risk
- lane_controls_written=false
- live_config_written=false
- percentage_risk_contract_fit_only=true
- hmac_signature_created=true only if regeneration is run
- signed_request_written=true only if regeneration is run
- signed_order_request_created=true only if regeneration is run
- signed_trading_request_created=true only if regeneration is run
- submit_allowed=false
- submit_attempted=false
- order_placed=false
- real_order_placed=false
- execution_attempted=false
- binance_order_endpoint_called=false
- binance_test_order_endpoint_called=false
- binance_account_endpoint_called=false
- binance_exchange_info_endpoint_called=true only if readonly refresh is run
- binance_mark_price_endpoint_called=true only if readonly refresh is run
- private_binance_endpoint_called=false
- signed_binance_endpoint_called=false
- network_allowed=true only for public readonly refresh when confirmed
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
logs/hammer_radar_forward/tiny_live_percentage_risk_contract_fit.ndjson

CONFIG:
Potentially update:
- configs/hammer_radar/tiny_live_risk_contracts.json

Only under exact confirmation.
Only to add percentage-model fields or stricter/equivalent resolved fields.

Do not update lane_controls.json in R262B.

DOCS:
Create:
docs/hammer_radar/live_readiness/R262B_TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_TRIPLET.md

Update:
docs/hammer_radar/live_readiness/R262A_TINY_LIVE_RISK_CONTRACT_FIX_CONTROLS_RECHECK.md
docs/hammer_radar/live_readiness/R261_TINY_LIVE_CONTROLS_ARMING_UI_AND_API.md
docs/hammer_radar/live_readiness/TINY_LIVE_REAL_SUBMIT_OPERATOR_RUNBOOK.md
docs/hammer_radar/live_readiness/PHASE_INDEX.md

FUTURE TASK:
Update:
codex_tasks/phases/R262_TINY_LIVE_FINAL_SUBMIT_CONSOLE.md

Rename/reframe in docs if needed as:
R263_TINY_LIVE_FINAL_SUBMIT_CONSOLE_AND_ARMING.md

TESTS:
Create:
tests/hammer_radar/test_tiny_live_percentage_risk_contract_fit_regeneration.py

Tests must cover:
- CLI preview returns JSON
- wrong confirmation rejects
- exact confirmation runs with monkeypatched child gates
- 88 wallet resolves to 44 margin at 50%
- full 88 wallet is not used as position margin
- resolved max notional remains 440
- leverage remains 10
- max loss remains <= 4.44
- quantity is reduced to fit <= 440 notional
- current 451 notional case is blocked before regeneration and fixed after sizing
- percentage schema update does not loosen risk
- no live controls mutation
- no submit/order/private Binance call
- no secrets in output

VALIDATION:
Run py_compile:
- src/app/hammer_radar/operator/tiny_live_percentage_risk_contract_fit_regeneration.py
- src/app/hammer_radar/operator/tiny_live_risk_contract_fix.py
- src/app/hammer_radar/operator/tiny_live_controls_arming.py
- src/app/hammer_radar/operator/inspect.py

Run focused:
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar/test_tiny_live_percentage_risk_contract_fit_regeneration.py

Run related:
PYTHONPATH=. .venv/bin/python -m pytest -q \
  tests/hammer_radar/test_tiny_live_risk_contract_fix.py \
  tests/hammer_radar/test_tiny_live_controls_arming.py \
  tests/hammer_radar/test_tiny_live_fresh_cycle_one_shot_orchestrator.py \
  tests/hammer_radar/test_tiny_live_actual_submit_gate.py

Run full:
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar

SMOKE:
Preview:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-percentage-risk-contract-fit \
  | jq '.status, .target_scope, .operator_intervention_model, .percentage_contract_model, .contract_fit_sizing_plan, .step_results, .output_validation, .go_no_go_packet, .contract_fit_matrix, .contract_fit_overall_status, .recommended_next_operator_move, .recommended_next_engineering_move, .do_not_run_yet, .safety'

Rejected:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-percentage-risk-contract-fit \
  --run-contract-fit-regeneration \
  --record-contract-fit-regeneration \
  --confirm-contract-fit-regeneration "wrong" \
  | jq '.status, .confirmation_valid, .contract_fit_regeneration_recorded, .safety'

Run:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-percentage-risk-contract-fit \
  --run-contract-fit-regeneration \
  --record-contract-fit-regeneration \
  --confirm-contract-fit-regeneration "I CONFIRM TINY LIVE PERCENTAGE RISK CONTRACT FIT REGENERATION ONLY; 88 USDT ISOLATED WALLET, 44 USDT POSITION MARGIN, 10X LEVERAGE, KEEP RISK SAME OR STRICTER; NO SUBMIT; NO ORDER; NO BINANCE ORDER CALL." \
  | jq '.status, .contract_fit_regeneration_recorded, .operator_intervention_model, .percentage_contract_model, .contract_fit_sizing_plan, .step_results, .output_validation, .go_no_go_packet, .contract_fit_matrix, .contract_fit_overall_status, .safety'

Secret leak check:
PYTHONPATH=. .venv/bin/python - <<'PY'
import os
from pathlib import Path

paths = [
    Path("logs/hammer_radar_forward/tiny_live_percentage_risk_contract_fit.ndjson"),
    Path("logs/hammer_radar_forward/tiny_live_fresh_context_signed_request_regeneration_gate.ndjson"),
    Path("logs/hammer_radar_forward/tiny_live_signed_request_write_gate.ndjson"),
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
git diff -- logs/hammer_radar_forward/candles_BTCUSDT_8m.ndjson || true
git diff -- logs/hammer_radar_forward/paper_outcomes.ndjson || true
git diff -- logs/hammer_radar_forward/strategy_performance.ndjson || true
git diff -- logs/hammer_radar_forward/strategy_promotion_status.ndjson || true

Expected artifacts:
git status --short configs/hammer_radar/tiny_live_risk_contracts.json || true
git status --short logs/hammer_radar_forward/tiny_live_percentage_risk_contract_fit.ndjson || true
git status --short logs/hammer_radar_forward/tiny_live_fresh_context_signed_request_regeneration_gate.ndjson || true
git status --short logs/hammer_radar_forward/tiny_live_submit_gate_preview.ndjson || true
git status --short logs/hammer_radar_forward/tiny_live_actual_submit_gate.ndjson || true
git status --short logs/hammer_radar_forward/tiny_live_controls_arming.ndjson || true

git diff -- configs/hammer_radar/tiny_live_risk_contracts.json || true
tail -n 5 logs/hammer_radar_forward/tiny_live_percentage_risk_contract_fit.ndjson 2>/dev/null || true

FINAL PHASE REPORT REQUIRED:
At the end, report:
- phase status
- files changed
- tests run
- smoke status
- safety status
- operator_intervention_model
- percentage_contract_model
- contract_fit_sizing_plan
- step_results
- output_validation
- go_no_go_packet
- contract_fit_matrix
- contract_fit_overall_status
- exact files mutated
- recommended next operator move
- recommended next engineering move
- do not commit
- do not run real submit

Aggressive mode:
Complete in one pass.
Respect operator model: 88 isolated wallet, 44 margin, 10x leverage.
Use percentages for durable contract model.
Do not loosen resolved risk.
Regenerate the triplet so it fits.
Do not submit.
Do not arm controls.
Do not call Binance order/private endpoints.
