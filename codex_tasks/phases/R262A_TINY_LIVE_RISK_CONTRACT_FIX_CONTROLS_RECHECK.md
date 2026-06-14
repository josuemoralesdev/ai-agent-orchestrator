You are in repo:
/home/josue/workspace/kernel/ai-agent-orchestrator-main

Follow:
- AGENTS.md
- codex_tasks/CODEX_RULES.md
- docs/hammer_radar/live_readiness/PHASE_INDEX.md
- docs/hammer_radar/live_readiness/TINY_LIVE_REAL_SUBMIT_OPERATOR_RUNBOOK.md
- docs/hammer_radar/live_readiness/R261_TINY_LIVE_CONTROLS_ARMING_UI_AND_API.md
- docs/hammer_radar/live_readiness/R260_TINY_LIVE_FRESH_CYCLE_ONE_SHOT_ORCHESTRATOR.md

PHASE:
R262A Tiny-Live Risk Contract Fix and Controls Recheck

BRANCH:
r262a-tiny-live-risk-contract-fix-controls-recheck

PHASE CLASSIFICATION:
Primary: RISK CONTRACT VALIDATION FIX / CONTROLS ARMING UNBLOCK
Secondary: CONFIG VALIDATION, OPERATOR CONTROL RECHECK, PRE-SUBMIT READINESS
Duplicate risk: EXTREME

WHY THIS PHASE EXISTS:
R261 Tiny-Live Controls Arming UI and API has been committed.

R261 successfully added:
- CLI controls review
- API endpoints:
  - GET /tiny-live/controls/review
  - POST /tiny-live/controls/review/record
  - POST /tiny-live/controls/arm
- UI/dashboard surface for Tiny Live Controls
- review ledger

R261 correctly refused to arm controls because:
- risk_contract_valid=false
- risk_contract_invalid_reasons=["risk_contract_invalid"]

R261 state:
- fresh_cycle_valid=true
- fresh_signed_request_available=true
- signed_request_fresh_enough_for_dry_preview=true
- dry_preview_recorded=true
- operator_should_arm_controls=false
- next_required_step=FIX_RISK_CONTRACT
- submit_allowed=false
- order_placed=false
- lane_controls_written=false

R262A must diagnose and fix the risk contract validation issue safely.

This phase may update:
- risk contract validation logic if the config is already semantically valid but validator is wrong
- docs explaining contract interpretation
- tests covering the official tiny-live risk contract
- optionally the risk contract config only if a schema field is missing/misnamed and the intended value is already known and safe

This phase must then re-run controls review and arm controls only if:
- risk contract is valid
- R260 fresh cycle is valid
- exact arming confirmation is used
- only lane_controls.json is changed
- no submit occurs

OFFICIAL LANE:
BTCUSDT|8m|short|ladder_close_50_618

KNOWN RISK CONTRACT VALUES FROM R261:
- margin budget: 44 USDT
- max notional: 440 USDT
- max loss: 4.44 USDT
- leverage: 10
- direction: short
- symbol: BTCUSDT
- timeframe: 8m
- entry mode: ladder_close_50_618

CORE INTENT:
Create a risk contract diagnostic/fix layer that:
1. Reads current tiny-live risk contract.
2. Reads current validator logic.
3. Explains exactly why R261 sees risk_contract_invalid.
4. Determines whether the issue is:
   - bad config
   - bad validator
   - schema mismatch
   - stale/incorrect lane key
   - missing lane field
   - invalid risk math
   - intentional hard block
5. Fixes the smallest correct surface.
6. Adds tests proving the official risk contract is valid only if truly safe.
7. Re-runs R261 controls review.
8. Allows controls arming only if risk contract becomes valid.
9. Records R262A diagnostic/fix ledger.
10. Produces R262B/R263 final submit console task update.

This phase is allowed to fix a validation bug.
This phase is not allowed to weaken risk limits.

NON-NEGOTIABLES:
- No Binance calls.
- No network calls.
- No Binance order endpoint.
- No Binance test order endpoint.
- No Binance account/private endpoint.
- No signed Binance endpoint.
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
- No scheduler/fisherman config write.
- No paper_outcomes append.
- No strategy performance append.
- No strategy promotion status append.
- No betrayal promotion.
- No alternate lane promotion.
- No official lane change.
- No submit_allowed=true.
- No order endpoint readiness claim.
- No sudo.
- Do not commit.
- Do not merge.
- Do not tag.
- Do not touch or stage AGENTS.md.

STRICT RISK LIMIT RULES:
Do not increase:
- margin budget above 44 USDT
- leverage above 10x
- max notional above 440 USDT
- max loss above 4.44 USDT

Do not loosen:
- reduce-only exit requirement
- exact 3-order triplet requirement
- manual confirmation requirement
- lane specificity
- no-submit from R262A

ALLOWED:
- Read configs and ledgers.
- Patch validation logic if wrong.
- Patch risk contract config only if schema mismatch is confirmed and values stay equal or stricter.
- Record diagnostic/fix ledger.
- Re-run R261 review.
- Arm lane controls only if risk contract becomes valid and exact arming phrase is given.
- Add tests/docs.
- Update future R262/R263 task docs.

EXACT DIAGNOSTIC CONFIRMATION PHRASE:
I CONFIRM TINY LIVE RISK CONTRACT DIAGNOSTIC RECORDING ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL.

EXACT FIX CONFIRMATION PHRASE:
I CONFIRM TINY LIVE RISK CONTRACT FIX FOR BTCUSDT 8M SHORT ONLY; KEEP RISK LIMITS SAME OR STRICTER; NO SUBMIT; NO ORDER; NO BINANCE CALL.

EXACT ARMING CONFIRMATION PHRASE, reused from R261:
I CONFIRM ARM TINY LIVE CONTROLS FOR BTCUSDT 8M SHORT ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL.

CAPABILITY SCAN FIRST:
Inspect:
- src/app/hammer_radar/operator/tiny_live_controls_arming.py
- src/app/hammer_radar/operator/tiny_live_fresh_cycle_one_shot_orchestrator.py
- src/app/hammer_radar/operator/tiny_live_actual_submit_gate.py
- src/app/hammer_radar/operator/inspect.py
- src/app/hammer_radar/operator/*risk* files
- src/app/hammer_radar/operator/*contract* files
- src/app/hammer_radar/operator/*lane* files
- src/app/hammer_radar/operator/*control* files
- src/app/hammer_radar/operator/*submit* files
- src/app/hammer_radar/operator/*live* files

Inspect configs:
- configs/hammer_radar/tiny_live_risk_contracts.json
- configs/hammer_radar/lane_controls.json
- configs/hammer_radar/*.json

Inspect ledgers:
- logs/hammer_radar_forward/tiny_live_controls_arming.ndjson
- logs/hammer_radar_forward/tiny_live_fresh_cycle_one_shot.ndjson
- logs/hammer_radar_forward/tiny_live_actual_submit_gate.ndjson
- logs/hammer_radar_forward/tiny_live_manual_submit_checkpoint.ndjson
- logs/hammer_radar_forward/tiny_live_operator_real_submit_runbook.ndjson

Inspect API/UI:
- src/app/hammer_radar/operator/approval_api.py

Inspect docs:
- docs/hammer_radar/live_readiness/R261_TINY_LIVE_CONTROLS_ARMING_UI_AND_API.md
- docs/hammer_radar/live_readiness/R260_TINY_LIVE_FRESH_CYCLE_ONE_SHOT_ORCHESTRATOR.md
- docs/hammer_radar/live_readiness/TINY_LIVE_REAL_SUBMIT_OPERATOR_RUNBOOK.md
- docs/hammer_radar/live_readiness/PHASE_INDEX.md

Inspect tests:
- tests/hammer_radar/test_tiny_live_controls_arming.py
- tests/hammer_radar/test_tiny_live_fresh_cycle_one_shot_orchestrator.py
- tests/hammer_radar/test_tiny_live_actual_submit_gate.py
- tests/hammer_radar/test_*risk* if present
- tests/hammer_radar/test_*contract* if present

REUSE / EXTEND:
Reuse:
- R261 risk contract loader and validation surface.
- Existing risk contract schema.
- Existing lane control writer.
- Existing safety object.
- Existing NDJSON append helpers.
- Existing API/UI routes if applicable.

Do not create a parallel risk model unless absolutely necessary.
Do not bypass R261.
Do not fake risk_contract_valid.

REQUIRED MODULE:
Create:
src/app/hammer_radar/operator/tiny_live_risk_contract_fix.py

Expose:
- build_tiny_live_risk_contract_diagnostic
- load_tiny_live_risk_contract_for_official_lane
- inspect_tiny_live_risk_contract_schema
- inspect_tiny_live_risk_contract_validator
- classify_tiny_live_risk_contract_invalid_reason
- build_tiny_live_risk_contract_fix_plan
- validate_tiny_live_risk_contract_fix_safety
- apply_tiny_live_risk_contract_fix_if_needed
- rerun_tiny_live_controls_review_after_fix
- rerun_tiny_live_controls_arming_after_fix
- append_tiny_live_risk_contract_fix_record
- load_tiny_live_risk_contract_fix_records
- classify_tiny_live_risk_contract_fix_status

CLI:
Wire into inspect.py as:
tiny-live-risk-contract-fix

Args:
- --record-risk-contract-diagnostic
- --confirm-risk-contract-diagnostic <phrase>
- --apply-risk-contract-fix
- --confirm-risk-contract-fix <phrase>
- --arm-controls-after-fix
- --confirm-arm-tiny-live-controls <phrase>
- --operator-id <id> optional default local_operator
- --reason <text> optional

Preview:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-risk-contract-fix

Record diagnostic:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-risk-contract-fix \
  --record-risk-contract-diagnostic \
  --confirm-risk-contract-diagnostic "I CONFIRM TINY LIVE RISK CONTRACT DIAGNOSTIC RECORDING ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL."

Apply fix:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-risk-contract-fix \
  --apply-risk-contract-fix \
  --confirm-risk-contract-fix "I CONFIRM TINY LIVE RISK CONTRACT FIX FOR BTCUSDT 8M SHORT ONLY; KEEP RISK LIMITS SAME OR STRICTER; NO SUBMIT; NO ORDER; NO BINANCE CALL."

Apply fix and arm controls:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-risk-contract-fix \
  --apply-risk-contract-fix \
  --confirm-risk-contract-fix "I CONFIRM TINY LIVE RISK CONTRACT FIX FOR BTCUSDT 8M SHORT ONLY; KEEP RISK LIMITS SAME OR STRICTER; NO SUBMIT; NO ORDER; NO BINANCE CALL." \
  --arm-controls-after-fix \
  --confirm-arm-tiny-live-controls "I CONFIRM ARM TINY LIVE CONTROLS FOR BTCUSDT 8M SHORT ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL." \
  --operator-id local_operator \
  --reason "R262A risk contract valid; R260 fresh cycle valid; preparing for R262 final submit console."

Rejected:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-risk-contract-fix \
  --apply-risk-contract-fix \
  --confirm-risk-contract-fix "wrong"

STATUS ENUM:
- TINY_LIVE_RISK_CONTRACT_FIX_READY
- TINY_LIVE_RISK_CONTRACT_DIAGNOSTIC_RECORDED
- TINY_LIVE_RISK_CONTRACT_FIX_APPLIED
- TINY_LIVE_RISK_CONTRACT_FIX_AND_CONTROLS_ARMING_RECORDED
- TINY_LIVE_RISK_CONTRACT_FIX_REJECTED
- TINY_LIVE_RISK_CONTRACT_FIX_BLOCKED
- TINY_LIVE_RISK_CONTRACT_FIX_ERROR

OVERALL STATUS ENUM:
- TINY_LIVE_RISK_CONTRACT_FIX_READY_FOR_DIAGNOSTIC
- TINY_LIVE_RISK_CONTRACT_FIX_READY_TO_APPLY
- TINY_LIVE_RISK_CONTRACT_VALID_CONTROLS_ARMING_REQUIRED
- TINY_LIVE_RISK_CONTRACT_VALID_CONTROLS_ARMED_R262_CONSOLE_REQUIRED
- TINY_LIVE_RISK_CONTRACT_FIX_REJECTED_BAD_CONFIRMATION
- TINY_LIVE_RISK_CONTRACT_FIX_BLOCKED_UNSAFE_LIMIT_CHANGE
- TINY_LIVE_RISK_CONTRACT_FIX_BLOCKED_UNKNOWN_SCHEMA
- UNKNOWN_NEEDS_MANUAL_REVIEW

OUTPUT MUST INCLUDE:
{
  "status": "...",
  "generated_at": "...",
  "record_risk_contract_diagnostic_requested": false,
  "apply_risk_contract_fix_requested": false,
  "arm_controls_after_fix_requested": false,
  "confirmation_valid": false,
  "risk_contract_diagnostic_recorded": false,
  "risk_contract_fix_applied": false,
  "controls_arming_recorded": false,
  "target_scope": {
    "official_lane_key": "BTCUSDT|8m|short|ladder_close_50_618",
    "symbol": "BTCUSDT",
    "timeframe": "8m",
    "direction": "short",
    "risk_contract_fix_only": true,
    "submit_allowed": false,
    "order_placed": false,
    "binance_order_endpoint_called": false,
    "network_allowed": false
  },
  "input_summary": {
    "risk_contract_found": true/false,
    "lane_controls_found": true/false,
    "r261_controls_review_found": true/false,
    "r260_one_shot_found": true/false,
    "r260_one_shot_valid": true/false
  },
  "risk_contract_before": {},
  "risk_contract_diagnostic": {
    "risk_contract_valid_before": true/false,
    "invalid_reasons_before": [],
    "schema_issue": true/false,
    "validator_issue": true/false,
    "config_issue": true/false,
    "risk_math_issue": true/false,
    "strictness_issue": true/false,
    "root_cause": "schema_mismatch|validator_bug|config_missing_field|unsafe_limits|unknown|already_valid"
  },
  "risk_contract_fix_plan": {
    "fix_required": true/false,
    "will_change_config": true/false,
    "will_change_validator": true/false,
    "will_keep_limits_same_or_stricter": true,
    "risk_limit_changes": {},
    "blocked_by": []
  },
  "risk_contract_fix_result": {
    "attempted": true/false,
    "succeeded": true/false,
    "risk_contract_valid_after": true/false,
    "invalid_reasons_after": [],
    "files_changed": [],
    "blocked_by": []
  },
  "controls_recheck_after_fix": {
    "attempted": true/false,
    "risk_contract_valid": true/false,
    "fresh_cycle_valid": true/false,
    "operator_should_arm_controls": true/false,
    "next_required_step": "ARM_CONTROLS|R262_FINAL_SUBMIT_CONSOLE|FIX_RISK_CONTRACT|WAIT"
  },
  "controls_arming_after_fix": {
    "attempted": true/false,
    "succeeded": true/false,
    "lane_controls_written": true/false,
    "official_lane_allowed": true/false,
    "live_execution_enabled": true/false,
    "kill_switch_allows_tiny_live": true/false,
    "blocked_by": []
  },
  "risk_contract_fix_matrix": {
    "r260_available": true/false,
    "risk_contract_valid_before": true/false,
    "risk_contract_valid_after": true/false,
    "limits_same_or_stricter": true/false,
    "controls_rechecked": true/false,
    "controls_armed": true/false,
    "submit_allowed": false,
    "order_placed": false,
    "blocked_by": []
  },
  "risk_contract_fix_overall_status": "...",
  "recommended_next_operator_move": "...",
  "recommended_next_engineering_move": "...",
  "do_not_run_yet": [
    "real submit from R262A",
    "real submit before R262 console",
    "real submit if risk contract remains invalid",
    "duplicate live submit"
  ],
  "safety": {...}
}

SAFETY OBJECT MUST INCLUDE:
- env_written=false
- env_mutated=false
- external_env_file_written=false
- config_written=true only if approved risk contract config fix or lane controls arming writes config
- risk_contract_config_written=true only if exact fix confirmation changes risk contract file
- lane_controls_written=true only if exact arming confirmation succeeds
- live_config_written=false unless existing schema treats lane controls as live config
- risk_contract_fix_only=true
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
- live_controls_armed_by_phase=true only if exact arming after fix succeeds
- secrets_read=false
- secrets_shown=false
- secrets_persisted=false
- secret_values_in_output=false
- global_live_flags_changed=false unless scoped lane live control schema requires it; if changed, document scoped only
- paper_live_separation_intact=true
- official_tiny_live_lane_changed=false
- official_tiny_live_lane_armed=true only if exact arming confirmation succeeds

LEDGER:
logs/hammer_radar_forward/tiny_live_risk_contract_fix.ndjson

CONFIG:
Potentially update:
- configs/hammer_radar/tiny_live_risk_contracts.json
- configs/hammer_radar/lane_controls.json

Only under exact confirmations.
Do not change risk limits to be looser.

API/UI:
If useful and existing API can safely expose it, add:
- GET /tiny-live/risk-contract/review
- POST /tiny-live/risk-contract/fix/record
- POST /tiny-live/risk-contract/fix/apply

No endpoint may submit, call Binance, sign, or place orders.

UI:
If existing Tiny Live Controls card exists:
- Add risk contract root cause display.
- Add “fix required / fixed / blocked” status.
- Add no submit button.
- Add link/section for next R262 console only if controls armed.

DOCS:
Create:
docs/hammer_radar/live_readiness/R262A_TINY_LIVE_RISK_CONTRACT_FIX_CONTROLS_RECHECK.md

Update:
docs/hammer_radar/live_readiness/R261_TINY_LIVE_CONTROLS_ARMING_UI_AND_API.md
docs/hammer_radar/live_readiness/TINY_LIVE_REAL_SUBMIT_OPERATOR_RUNBOOK.md
docs/hammer_radar/live_readiness/PHASE_INDEX.md

FUTURE TASK:
Update:
codex_tasks/phases/R262_TINY_LIVE_FINAL_SUBMIT_CONSOLE.md

R262 should:
- require R262A risk contract valid
- require controls armed
- require R260 fresh cycle valid
- show final signed triplet and freshness
- still no auto-submit by default

TESTS:
Create:
tests/hammer_radar/test_tiny_live_risk_contract_fix.py

Tests must cover:
- CLI preview returns JSON
- diagnostic record exact phrase records only
- wrong fix phrase rejects
- fix plan detects root cause
- unsafe limit increase is blocked
- validator/config fix makes official contract valid if safe
- exact fix confirmation applies minimal safe fix
- exact fix + arm controls writes only intended config files
- lane controls preserve unrelated keys
- no Binance/network/signing/submit/order
- no secrets in output
- API endpoints if added
- UI risk contract display if added

VALIDATION:
Run py_compile:
- src/app/hammer_radar/operator/tiny_live_risk_contract_fix.py
- src/app/hammer_radar/operator/tiny_live_controls_arming.py
- src/app/hammer_radar/operator/inspect.py
- src/app/hammer_radar/operator/approval_api.py if edited

Run focused:
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar/test_tiny_live_risk_contract_fix.py

Run related:
PYTHONPATH=. .venv/bin/python -m pytest -q \
  tests/hammer_radar/test_tiny_live_controls_arming.py \
  tests/hammer_radar/test_tiny_live_fresh_cycle_one_shot_orchestrator.py \
  tests/hammer_radar/test_tiny_live_actual_submit_gate.py

Run full:
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar

SMOKE:
Preview:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-risk-contract-fix \
  | jq '.status, .target_scope, .input_summary, .risk_contract_diagnostic, .risk_contract_fix_plan, .risk_contract_fix_result, .controls_recheck_after_fix, .controls_arming_after_fix, .risk_contract_fix_matrix, .risk_contract_fix_overall_status, .recommended_next_operator_move, .recommended_next_engineering_move, .do_not_run_yet, .safety'

Record diagnostic:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-risk-contract-fix \
  --record-risk-contract-diagnostic \
  --confirm-risk-contract-diagnostic "I CONFIRM TINY LIVE RISK CONTRACT DIAGNOSTIC RECORDING ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL." \
  | jq '.status, .risk_contract_diagnostic_recorded, .risk_contract_diagnostic, .risk_contract_fix_plan, .risk_contract_fix_overall_status, .safety'

Rejected fix:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-risk-contract-fix \
  --apply-risk-contract-fix \
  --confirm-risk-contract-fix "wrong" \
  | jq '.status, .confirmation_valid, .risk_contract_fix_applied, .risk_contract_fix_result, .safety'

Apply fix:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-risk-contract-fix \
  --apply-risk-contract-fix \
  --confirm-risk-contract-fix "I CONFIRM TINY LIVE RISK CONTRACT FIX FOR BTCUSDT 8M SHORT ONLY; KEEP RISK LIMITS SAME OR STRICTER; NO SUBMIT; NO ORDER; NO BINANCE CALL." \
  | jq '.status, .risk_contract_fix_applied, .risk_contract_diagnostic, .risk_contract_fix_plan, .risk_contract_fix_result, .controls_recheck_after_fix, .risk_contract_fix_matrix, .risk_contract_fix_overall_status, .safety'

Apply fix and arm:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-risk-contract-fix \
  --apply-risk-contract-fix \
  --confirm-risk-contract-fix "I CONFIRM TINY LIVE RISK CONTRACT FIX FOR BTCUSDT 8M SHORT ONLY; KEEP RISK LIMITS SAME OR STRICTER; NO SUBMIT; NO ORDER; NO BINANCE CALL." \
  --arm-controls-after-fix \
  --confirm-arm-tiny-live-controls "I CONFIRM ARM TINY LIVE CONTROLS FOR BTCUSDT 8M SHORT ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL." \
  --operator-id local_operator \
  --reason "R262A risk contract valid; R260 fresh cycle valid; preparing for R262 final submit console." \
  | jq '.status, .risk_contract_fix_applied, .controls_arming_recorded, .risk_contract_fix_result, .controls_recheck_after_fix, .controls_arming_after_fix, .risk_contract_fix_matrix, .risk_contract_fix_overall_status, .safety'

Secret leak check:
PYTHONPATH=. .venv/bin/python - <<'PY'
import os
from pathlib import Path

paths = [
    Path("logs/hammer_radar_forward/tiny_live_risk_contract_fix.ndjson"),
    Path("logs/hammer_radar_forward/tiny_live_controls_arming.ndjson"),
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
git diff -- logs/hammer_radar_forward/candles_BTCUSDT_8m.ndjson || true
git diff -- logs/hammer_radar_forward/paper_outcomes.ndjson || true
git diff -- logs/hammer_radar_forward/strategy_performance.ndjson || true
git diff -- logs/hammer_radar_forward/strategy_promotion_status.ndjson || true

Expected artifacts:
git status --short configs/hammer_radar/tiny_live_risk_contracts.json || true
git status --short configs/hammer_radar/lane_controls.json || true
git status --short logs/hammer_radar_forward/tiny_live_risk_contract_fix.ndjson || true
git status --short logs/hammer_radar_forward/tiny_live_controls_arming.ndjson || true
tail -n 5 logs/hammer_radar_forward/tiny_live_risk_contract_fix.ndjson 2>/dev/null || true

FINAL PHASE REPORT REQUIRED:
At the end, report:
- phase status
- files changed
- tests run
- smoke status
- safety status
- risk_contract_diagnostic
- risk_contract_fix_plan
- risk_contract_fix_result
- controls_recheck_after_fix
- controls_arming_after_fix
- risk_contract_fix_matrix
- risk_contract_fix_overall_status
- API/UI endpoints added
- exact files mutated
- recommended next operator move
- recommended next engineering move
- do not commit
- do not run real submit

Aggressive mode:
Complete in one pass.
Fix the risk contract blocker without weakening risk.
Then recheck controls.
Arm controls only if valid and exact arming confirmation is present.
Do not submit.
Do not call Binance.
Do not sign.
Do not place orders.
