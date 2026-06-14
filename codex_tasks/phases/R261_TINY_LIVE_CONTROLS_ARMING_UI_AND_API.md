You are in repo:
/home/josue/workspace/kernel/ai-agent-orchestrator-main

Follow:
- AGENTS.md
- codex_tasks/CODEX_RULES.md
- docs/hammer_radar/live_readiness/PHASE_INDEX.md
- docs/hammer_radar/live_readiness/TINY_LIVE_REAL_SUBMIT_OPERATOR_RUNBOOK.md

PHASE:
R261 Tiny-Live Controls Arming UI and API

BRANCH:
r261-tiny-live-controls-arming-ui-api

PHASE CLASSIFICATION:
Primary: UI/API LIVE-CONTROL ARMING REVIEW SURFACE
Secondary: CONTROLLED LANE ARMING, RISK CONTRACT VISIBILITY, PRE-SUBMIT OPERATOR COCKPIT
Duplicate risk: EXTREME

WHY THIS PHASE EXISTS:
R260 Tiny-Live Fresh Cycle One-Shot Orchestrator has been committed.

R260 successfully compressed the fresh cycle:
- R253 readonly refresh succeeded
- R253B regeneration succeeded
- R254 submit preview succeeded
- R255 dry preview succeeded
- R258 manual checkpoint re-check succeeded
- one_shot_output_validation.valid=true
- fresh_signed_request_available=true
- signed_request_fresh_enough_for_dry_preview=true

R260 did NOT submit and did NOT arm live controls.

R260 final state requires:
- LIVE_CONTROL_REVIEW
- official lane tiny-live arming review
- live execution review
- risk contract invalid visibility/fix path
- operator cockpit/UI

R261 must build the operator-facing UI/API for intentional tiny-live lane arming.

This phase may create a review/arming surface.
This phase may write live-control arming intent ONLY through a strict explicit confirmation path.
This phase must not submit.
This phase must not call Binance.
This phase must not sign.
This phase must not place orders.

OFFICIAL LANE:
BTCUSDT|8m|short|ladder_close_50_618

KNOWN R260 NEXT STEP:
LIVE_CONTROL_REVIEW

CURRENT KNOWN BLOCKERS TO SURFACE:
- official_lane_not_tiny_live
- live_execution_not_enabled
- risk_contract_invalid
- submit_still_forbidden

CORE INTENT:
Create a local operator UI/API and CLI checkpoint that:
1. Reads latest R260 one-shot fresh cycle result.
2. Reads latest R255 dry preview.
3. Reads tiny-live risk contract.
4. Reads lane controls.
5. Shows whether official lane is armed for tiny-live.
6. Shows whether live execution is enabled.
7. Shows whether kill switch allows tiny-live.
8. Shows whether the risk contract is valid for the official lane.
9. Shows whether signed request is fresh enough.
10. Shows whether submit remains forbidden.
11. Provides a deliberate operator arming endpoint/action for lane controls only.
12. Records an arming review ledger.
13. Provides UI card/state suitable for dashboard.
14. Produces R262 final submit console task.

This phase must separate:
- REVIEW mode: no mutation
- ARMING mode: exact confirmation required, lane-controls mutation only if allowed by existing project safety model
- SUBMIT: forbidden

If an existing lane-controls writer exists, reuse it.
If no writer exists, implement a minimal safe writer that only updates the official lane tiny-live arming fields, never anything else.

NON-NEGOTIABLES:
- No Binance calls.
- No network calls except local API/UI route.
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
- No risk contract config write unless a read-only validation bug requires docs only.
- No scheduler/fisherman config write.
- No kill switch disable unless existing lane-controls model explicitly supports tiny-live arm with audit.
- No global live flag changes unless existing lane-controls model explicitly supports local tiny-live scoped arm with audit.
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

ALLOWED:
- Read local ledgers/configs.
- Add UI/API review surfaces.
- Add strictly scoped arming route if exact confirmation is provided.
- Append R261 review/arming ledger.
- Add docs/tests.
- Create R262 future task.

EXACT REVIEW CONFIRMATION PHRASE:
I CONFIRM TINY LIVE CONTROLS REVIEW RECORDING ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL.

EXACT ARMING CONFIRMATION PHRASE:
I CONFIRM ARM TINY LIVE CONTROLS FOR BTCUSDT 8M SHORT ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL.

ARMING RULES:
R261 arming may only:
- mark the exact official lane BTCUSDT|8m|short|ladder_close_50_618 as tiny-live allowed
- record operator intent
- record timestamp
- record source phase R261
- preserve all unrelated lanes
- preserve all unrelated configs
- preserve paper/live separation
- never set submit_allowed=true
- never place order
- never call Binance

If existing config uses different fields, adapt to existing schema. Do not invent a conflicting schema without migration safety.

CAPABILITY SCAN FIRST:
Inspect:
- src/app/hammer_radar/operator/tiny_live_fresh_cycle_one_shot_orchestrator.py
- src/app/hammer_radar/operator/tiny_live_fresh_cycle_checkpoint.py
- src/app/hammer_radar/operator/tiny_live_manual_submit_checkpoint.py
- src/app/hammer_radar/operator/tiny_live_final_pre_submit_arming_drill.py
- src/app/hammer_radar/operator/tiny_live_actual_submit_gate.py
- src/app/hammer_radar/operator/tiny_live_operator_real_submit_runbook.py
- src/app/hammer_radar/operator/inspect.py
- src/app/hammer_radar/operator/*lane* files
- src/app/hammer_radar/operator/*control* files
- src/app/hammer_radar/operator/*arming* files
- src/app/hammer_radar/operator/*live* files
- src/app/hammer_radar/operator/*risk* files
- src/app/hammer_radar/operator/*kill* files
- src/app/hammer_radar/operator/*submit* files

Inspect API/UI:
- src/app/hammer_radar/operator/approval_api.py
- src/app/hammer_radar/operator/*api* files
- src/app/hammer_radar/operator/*dashboard* files
- src/app/hammer_radar/operator/*ui* files
- templates if present
- static if present
- frontend routes if present

Inspect configs:
- configs/hammer_radar/tiny_live_risk_contracts.json
- configs/hammer_radar/lane_controls.json
- configs/hammer_radar/*.json

Inspect ledgers/logs:
- logs/hammer_radar_forward/tiny_live_fresh_cycle_one_shot.ndjson
- logs/hammer_radar_forward/tiny_live_actual_submit_gate.ndjson
- logs/hammer_radar_forward/tiny_live_manual_submit_checkpoint.ndjson
- logs/hammer_radar_forward/tiny_live_operator_real_submit_runbook.ndjson
- logs/hammer_radar_forward/tiny_live_submit_gate_preview.ndjson
- logs/hammer_radar_forward/tiny_live_fresh_context_signed_request_regeneration_gate.ndjson

Inspect docs:
- docs/hammer_radar/live_readiness/R260_TINY_LIVE_FRESH_CYCLE_ONE_SHOT_ORCHESTRATOR.md
- docs/hammer_radar/live_readiness/R259_TINY_LIVE_FRESH_CYCLE_CHECKPOINT.md
- docs/hammer_radar/live_readiness/R258_TINY_LIVE_MANUAL_SUBMIT_CHECKPOINT.md
- docs/hammer_radar/live_readiness/TINY_LIVE_REAL_SUBMIT_OPERATOR_RUNBOOK.md
- docs/hammer_radar/live_readiness/PHASE_INDEX.md

Inspect tests:
- tests/hammer_radar/test_tiny_live_fresh_cycle_one_shot_orchestrator.py
- tests/hammer_radar/test_tiny_live_actual_submit_gate.py
- tests/hammer_radar/test_*lane* if present
- tests/hammer_radar/test_*control* if present
- tests/hammer_radar/test_*arming* if present
- tests/hammer_radar/test_*api* if present
- tests/hammer_radar/test_*dashboard* if present

REUSE / EXTEND:
Reuse:
- existing lane control schema
- existing FastAPI app/router if present
- existing operator dashboard conventions if present
- existing ledger append helper
- existing safety object conventions
- R260 output summary
- R255 dry preview state
- R258 manual checkpoint state

Do not duplicate large blocks if existing helpers can be imported.

REQUIRED MODULE:
Create:
src/app/hammer_radar/operator/tiny_live_controls_arming.py

Expose:
- build_tiny_live_controls_review
- load_latest_tiny_live_fresh_cycle_one_shot
- load_latest_tiny_live_actual_submit_gate
- load_tiny_live_lane_controls
- load_tiny_live_risk_contract
- summarize_tiny_live_controls_state
- summarize_tiny_live_risk_contract_state
- summarize_tiny_live_freshness_state
- build_tiny_live_controls_review_packet
- build_tiny_live_controls_arming_plan
- validate_tiny_live_controls_arming_request
- apply_tiny_live_controls_arming_request
- append_tiny_live_controls_review_record
- append_tiny_live_controls_arming_record
- load_tiny_live_controls_arming_records
- classify_tiny_live_controls_review_status
- classify_tiny_live_controls_arming_status

CLI:
Wire into inspect.py as:
tiny-live-controls-arming

Args:
- --record-controls-review
- --confirm-tiny-live-controls-review <phrase>
- --arm-tiny-live-controls
- --confirm-arm-tiny-live-controls <phrase>
- --operator-id <id> optional, default local_operator
- --reason <text> optional

Preview:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-controls-arming

Record review:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-controls-arming \
  --record-controls-review \
  --confirm-tiny-live-controls-review "I CONFIRM TINY LIVE CONTROLS REVIEW RECORDING ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL."

Arm controls:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-controls-arming \
  --arm-tiny-live-controls \
  --confirm-arm-tiny-live-controls "I CONFIRM ARM TINY LIVE CONTROLS FOR BTCUSDT 8M SHORT ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL." \
  --operator-id local_operator \
  --reason "R260 fresh cycle valid; preparing for R262 final submit console."

Rejected:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-controls-arming \
  --arm-tiny-live-controls \
  --confirm-arm-tiny-live-controls "wrong"

STATUS ENUM:
- TINY_LIVE_CONTROLS_REVIEW_READY
- TINY_LIVE_CONTROLS_REVIEW_RECORDED
- TINY_LIVE_CONTROLS_ARMING_RECORDED
- TINY_LIVE_CONTROLS_ARMING_REJECTED
- TINY_LIVE_CONTROLS_ARMING_BLOCKED
- TINY_LIVE_CONTROLS_ARMING_ERROR

OVERALL STATUS ENUM:
- TINY_LIVE_CONTROLS_READY_FOR_REVIEW
- TINY_LIVE_CONTROLS_REVIEW_RECORDED_ARMING_REQUIRED
- TINY_LIVE_CONTROLS_ARMED_R262_FINAL_CONSOLE_REQUIRED
- TINY_LIVE_CONTROLS_ARMING_REJECTED_BAD_CONFIRMATION
- TINY_LIVE_CONTROLS_ARMING_BLOCKED_BY_RISK_CONTRACT
- TINY_LIVE_CONTROLS_ARMING_BLOCKED_BY_MISSING_R260
- UNKNOWN_NEEDS_MANUAL_REVIEW

OUTPUT MUST INCLUDE:
{
  "status": "...",
  "generated_at": "...",
  "record_controls_review_requested": false,
  "arm_tiny_live_controls_requested": false,
  "confirmation_valid": false,
  "controls_review_recorded": false,
  "controls_arming_recorded": false,
  "target_scope": {
    "official_lane_key": "BTCUSDT|8m|short|ladder_close_50_618",
    "symbol": "BTCUSDT",
    "timeframe": "8m",
    "direction": "short",
    "controls_arming_only": true,
    "submit_allowed": false,
    "order_placed": false,
    "binance_order_endpoint_called": false,
    "network_allowed": false
  },
  "input_summary": {
    "r260_one_shot_found": true/false,
    "r260_one_shot_valid": true/false,
    "r255_dry_preview_found": true/false,
    "lane_controls_found": true/false,
    "risk_contract_found": true/false
  },
  "controls_state": {
    "official_lane_allowed": true/false,
    "live_execution_enabled": true/false,
    "kill_switch_allows_tiny_live": true/false,
    "manual_arming_required": true/false,
    "armed_by_this_phase": true/false
  },
  "risk_contract_state": {
    "risk_contract_found": true/false,
    "risk_contract_valid": true/false,
    "risk_contract_invalid_reasons": [],
    "tiny_live_margin_budget_usdt": null,
    "tiny_live_max_notional_usdt": null,
    "tiny_live_max_loss_usdt": null,
    "leverage": null
  },
  "freshness_state": {
    "fresh_cycle_valid": true/false,
    "fresh_signed_request_available": true/false,
    "signed_request_fresh_enough_for_dry_preview": true/false,
    "dry_preview_recorded": true/false
  },
  "controls_review_packet": {
    "submit_still_forbidden": true,
    "operator_should_submit_now": false,
    "operator_should_review_risk_contract": true/false,
    "operator_should_arm_controls": true/false,
    "operator_should_open_r262_console_next": true/false,
    "next_required_step": "ARM_CONTROLS|FIX_RISK_CONTRACT|RERUN_R260|R262_FINAL_SUBMIT_CONSOLE|WAIT"
  },
  "arming_plan": {
    "will_write_lane_controls": true/false,
    "will_change_official_lane_only": true/false,
    "will_enable_live_execution": true/false,
    "will_disable_kill_switch": false,
    "will_submit": false,
    "will_place_order": false
  },
  "arming_result": {
    "attempted": true/false,
    "succeeded": true/false,
    "blocked_by": [],
    "lane_controls_written": true/false,
    "before": {},
    "after": {}
  },
  "controls_arming_matrix": {
    "r260_available": true/false,
    "risk_contract_valid": true/false,
    "fresh_cycle_valid": true/false,
    "official_lane_allowed": true/false,
    "live_execution_enabled": true/false,
    "kill_switch_allows_tiny_live": true/false,
    "record_confirmed": true/false,
    "review_recorded": true/false,
    "arming_recorded": true/false,
    "submit_allowed": false,
    "order_placed": false,
    "blocked_by": []
  },
  "controls_arming_overall_status": "...",
  "recommended_next_operator_move": "...",
  "recommended_next_engineering_move": "...",
  "do_not_run_yet": [
    "real submit from R261",
    "real submit before R262 console",
    "real submit while risk contract invalid",
    "duplicate live submit"
  ],
  "safety": {...}
}

SAFETY OBJECT MUST INCLUDE:
- env_written=false
- env_mutated=false
- external_env_file_written=false
- config_written=true only if lane_controls.json was intentionally written under exact arming confirmation
- risk_contract_config_written=false
- lane_controls_written=true only if exact arming confirmation succeeds
- live_config_written=false unless existing schema treats lane_controls as live config; if so document clearly
- controls_arming_only=true
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
- kill_switch_disabled=false unless existing tiny-live arming means kill switch allows lane; prefer field kill_switch_allows_tiny_live=true without global disable
- live_controls_armed_by_phase=true only on exact arming confirmation
- secrets_read=false
- secrets_shown=false
- secrets_persisted=false
- secret_values_in_output=false
- global_live_flags_changed=false unless existing schema requires scoped live_execution_enabled; if changed, mark scoped only and document
- paper_live_separation_intact=true
- official_tiny_live_lane_changed=false
- official_tiny_live_lane_armed=true only on exact arming confirmation

LEDGER:
logs/hammer_radar_forward/tiny_live_controls_arming.ndjson

CONFIG:
If arming succeeds, update exact file only:
configs/hammer_radar/lane_controls.json

Do not update risk contract file in R261.

API/UI:
Add FastAPI endpoints to existing approval/operator API if present.

Required endpoints:
- GET /tiny-live/controls/review
- POST /tiny-live/controls/review/record
- POST /tiny-live/controls/arm

Behavior:
- GET returns same review packet as CLI preview.
- record review requires exact phrase.
- arm requires exact arming phrase, operator_id, reason.
- all endpoints must return JSON.
- no endpoint may submit.
- no endpoint may call Binance.
- no endpoint may sign.

If there is an existing dashboard HTML/template system:
- Add a simple section/card for Tiny Live Controls.
- Show:
  - official lane
  - fresh cycle valid
  - risk contract valid/invalid reasons
  - live execution enabled
  - official lane allowed
  - kill switch allows tiny-live
  - current blockers
  - next required step
  - “submit forbidden from this screen”
- Do not add a submit button in R261.
- Add review/arm forms only if existing UI pattern supports it.

DOCS:
Create:
docs/hammer_radar/live_readiness/R261_TINY_LIVE_CONTROLS_ARMING_UI_AND_API.md

Update:
docs/hammer_radar/live_readiness/TINY_LIVE_REAL_SUBMIT_OPERATOR_RUNBOOK.md

Update:
docs/hammer_radar/live_readiness/PHASE_INDEX.md

FUTURE TASK:
Update existing:
codex_tasks/phases/R262_TINY_LIVE_FINAL_SUBMIT_CONSOLE.md

R262 should:
- consume R261 controls arming result
- show final signed triplet
- show freshness age
- show all blockers
- show exact submit command
- no auto-submit by default
- prepare operator final console

TESTS:
Create:
tests/hammer_radar/test_tiny_live_controls_arming.py

Tests must cover:
- CLI preview returns JSON
- review record exact phrase records review only
- wrong review phrase rejects
- wrong arming phrase rejects
- exact arming phrase writes only lane_controls.json in temp config path or monkeypatch
- arming preserves unrelated lanes/config keys
- no Binance/network/signing/submit/order
- risk contract invalid blocks or clearly surfaces blocked_by depending existing policy
- controls review says submit forbidden
- API GET review returns JSON if API exists
- API POST arm requires confirmation if API exists
- UI/card includes no submit button if UI exists
- no secrets in output

VALIDATION:
Run py_compile:
- src/app/hammer_radar/operator/tiny_live_controls_arming.py
- src/app/hammer_radar/operator/inspect.py
- any edited API/UI files

Run focused:
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar/test_tiny_live_controls_arming.py

Run related:
PYTHONPATH=. .venv/bin/python -m pytest -q \
  tests/hammer_radar/test_tiny_live_fresh_cycle_one_shot_orchestrator.py \
  tests/hammer_radar/test_tiny_live_actual_submit_gate.py \
  tests/hammer_radar/test_tiny_live_manual_submit_checkpoint.py

Run API/UI related tests if present.

Run full:
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar

SMOKE:
Preview:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-controls-arming \
  | jq '.status, .target_scope, .input_summary, .controls_state, .risk_contract_state, .freshness_state, .controls_review_packet, .arming_plan, .arming_result, .controls_arming_matrix, .controls_arming_overall_status, .recommended_next_operator_move, .recommended_next_engineering_move, .do_not_run_yet, .safety'

Record review:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-controls-arming \
  --record-controls-review \
  --confirm-tiny-live-controls-review "I CONFIRM TINY LIVE CONTROLS REVIEW RECORDING ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL." \
  | jq '.status, .controls_review_recorded, .controls_review_packet, .controls_arming_matrix, .controls_arming_overall_status, .safety'

Rejected arming:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-controls-arming \
  --arm-tiny-live-controls \
  --confirm-arm-tiny-live-controls "wrong" \
  | jq '.status, .confirmation_valid, .controls_arming_recorded, .arming_result, .safety'

Arming command:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-controls-arming \
  --arm-tiny-live-controls \
  --confirm-arm-tiny-live-controls "I CONFIRM ARM TINY LIVE CONTROLS FOR BTCUSDT 8M SHORT ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL." \
  --operator-id local_operator \
  --reason "R260 fresh cycle valid; preparing for R262 final submit console." \
  | jq '.status, .controls_arming_recorded, .controls_state, .risk_contract_state, .freshness_state, .arming_result, .controls_arming_matrix, .controls_arming_overall_status, .safety'

Secret leak check:
PYTHONPATH=. .venv/bin/python - <<'PY'
import os
from pathlib import Path

paths = [
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
git diff -- configs/hammer_radar/tiny_live_risk_contracts.json || true
git diff -- logs/hammer_radar_forward/candles_BTCUSDT_8m.ndjson || true
git diff -- logs/hammer_radar_forward/paper_outcomes.ndjson || true
git diff -- logs/hammer_radar_forward/strategy_performance.ndjson || true
git diff -- logs/hammer_radar_forward/strategy_promotion_status.ndjson || true

Expected artifacts:
git status --short configs/hammer_radar/lane_controls.json || true
git status --short logs/hammer_radar_forward/tiny_live_controls_arming.ndjson || true
tail -n 5 logs/hammer_radar_forward/tiny_live_controls_arming.ndjson 2>/dev/null || true

FINAL PHASE REPORT REQUIRED:
At the end, report:
- phase status
- files changed
- tests run
- smoke status
- safety status
- controls_state
- risk_contract_state
- freshness_state
- controls_review_packet
- arming_plan
- arming_result
- controls_arming_matrix
- controls_arming_overall_status
- API/UI endpoints added
- exact files mutated
- recommended next operator move
- recommended next engineering move
- do not commit
- do not run real submit

Aggressive mode:
Complete in one pass.
Build UI/API if existing surface allows it.
Build CLI regardless.
Do not submit.
Do not call Binance.
Do not sign.
Do not place orders.
Only mutate lane_controls.json under exact arming confirmation.
