# R306 Capability Reuse Report

## Phase Classification

- Primary classification: DIAGNOSTIC / AUDIT
- Secondary classification: WIRING / INTEGRATION
- Duplicate risk level: MEDIUM
- Reason: R306 resembles R304 Strategy Lab preview, R305 variant ranking, R303 final authorization, and existing dry-run scheduler/timer surfaces. The implementation therefore extends those read-only surfaces instead of creating an execution path.

## Existing Reusable Modules

- `strategy_lab_variant_test_pack.py`: R305 direct-evidence variant ranking, top candidate scoring, confidence classes, and safety-field pattern.
- `strategy_lab_preview.py`: R304 preview lane model, current first Tiny Live lane constant, lab-only expansion semantics, and betrayal blocking policy.
- `tiny_live_final_authorization_gate.py`: final gate status, blockers, current candidate lane, and explicit submit/final-command lock state.
- `tiny_live_final_console.py`: operator-facing safety cockpit and final gate composition patterns.
- `tiny_live_fresh_trigger_watch.py`: current real/fresh candidate visibility without submit or arming mutation.
- `tiny_live_strategy_lane_selection.py`: exact lane key construction and exact risk-contract lookup/validation preview.
- `tiny_live_risk_contract.py`: local non-secret risk contract config loading and validation conventions.
- `tiny_live_risk_contract_validation.py`: shared risk-contract interpretation and blocker naming.
- `tiny_live_autonomous_trigger_scheduler.py`: dry-run scheduler safety model and append-only ledger posture.
- `tiny_live_autonomous_trigger_scheduler_timer_health.py`: read-only timer health status and `TIMER_HEALTH_ACTIVE` requirement.
- `inspect.py`: established command dispatch pattern for operator inspection surfaces.

## Existing Safety Gates

- Final authorization gate keeps `submit_allowed=false` and `final_command_available=false` unless all prior gates pass; R306 forcibly reports both false.
- Fresh trigger watch is visibility-only and does not submit, sign, or mutate.
- Exact risk-contract status requires an exact lane match and valid contract before any future path can proceed.
- Timer health requires an active dry-run scheduler timer before future observation is considered healthy.
- Existing R304/R305 safety fields already forbid live execution, live orders, Binance order/test-order endpoints, leverage changes, margin changes, secret output, and executable payloads.

## Existing Dry-Run Scheduler Surfaces

- R288 scheduler records dry-run loop iterations only.
- R292 timer health checks installed systemd timer state with read-only commands only.
- R293 timer health hardened the current journal window.
- R306 consumes timer health as a requirement but does not start, stop, enable, disable, or edit systemd units.

## Duplicate Risks

- Duplicate with R304 Strategy Lab preview: mitigated by reusing R305/R304 evidence and only adding the expansion-specific lane-role matrix.
- Duplicate with R305 Variant Test Pack: mitigated by consuming R305 rows rather than rescoring variants.
- Duplicate with R303 final gate: mitigated by summarizing final gate state instead of recomputing final authorization.
- Duplicate with risk-contract preview/write-gate phases: mitigated by using exact contract validation read-only and never writing `tiny_live_risk_contracts.json`.
- Duplicate with scheduler phases: mitigated by requiring timer health but not scheduling or observing multiple lanes yet.

## Selected Extension Points

- New module: `src/app/hammer_radar/operator/eligible_lane_expansion_dry_run_preview.py`
- Inspect command: `eligible-lane-expansion-dry-run-preview`
- Output ledger: `logs/hammer_radar_forward/eligible_lane_expansion_dry_run_preview.ndjson`
- Operator script: `scripts/hammer_print_r306_eligible_lane_expansion_preview.sh`
- Documentation: `docs/hammer_radar/live_readiness/R306_ELIGIBLE_LANE_EXPANSION_DRY_RUN_PREVIEW.md`
- Tests: `tests/hammer_radar/test_eligible_lane_expansion_dry_run_preview.py`

## Why This Is Not Live Expansion

R306 does not change `configs/hammer_radar/autonomous_arming_state.json`, does not write `configs/hammer_radar/tiny_live_risk_contracts.json`, does not arm any lane, does not create final commands, does not create executable payloads, and does not call Binance order, test-order, leverage, or margin endpoints. The current first Tiny Live lane remains `BTCUSDT|44m|long|ladder_close_50_618`. Expansion candidates are labeled for dry-run preview or watch-only review, with live blockers recorded explicitly.
