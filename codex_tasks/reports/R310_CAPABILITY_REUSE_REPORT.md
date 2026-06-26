# R310 Capability Reuse Report

## Phase Classification

- Primary classification: `WIRING / INTEGRATION`
- Secondary classification: `DIAGNOSTIC / AUDIT`
- Duplicate risk level: `MEDIUM`
- Reason: R310 composes existing dry-run expansion lane lists, exact risk-contract validation, fresh-trigger visibility, and timer health into a new observation packet. It does not replace the existing R306 preview, R307 risk-contract repair, R309 write gate, R286 fresh-trigger watch, or R292 timer-health surface.

## Existing Surfaces Checked

### Configs

- `configs/hammer_radar/tiny_live_risk_contracts.json`
  - Contains 10 risk-contract rows.
  - The 8 R309 target rows are present.
  - Each R309 target row has `live_execution_enabled=false`, `allow_live_orders=false`, `max_loss_usdt=4.44`, `margin_budget_usdt=8`, `leverage=10`, and `max_position_notional_usdt=80`.
- `configs/hammer_radar/autonomous_arming_state.json`
  - Current `armed_lane_key` remains `BTCUSDT|44m|long|ladder_close_50_618`.
  - `auto_execute_mode` is `dry_run_only`.
  - The config was read for scan only and is not mutated by R310.

### Existing Dry-Run Scheduler Surfaces

- `src/app/hammer_radar/operator/tiny_live_autonomous_trigger_scheduler.py`
  - Existing one-shot and bounded-loop dry-run scheduler for the single current tiny-live lane.
  - Append-only scheduler ledger pattern reused conceptually.
  - Not extended directly because R310 observes multiple lanes and must not arm or invoke trigger-loop behavior.
- `src/app/hammer_radar/operator/tiny_live_autonomous_trigger_scheduler_timer_health.py`
  - Existing read-only systemd timer health surface.
  - R310 consumes its packet for `timer_health_status` and `timer_active`.

### Existing Fresh-Trigger Watch Logic

- `src/app/hammer_radar/operator/tiny_live_fresh_trigger_watch.py`
  - Existing visibility-only current candidate packet.
  - R310 consumes latest/not-checked fresh-trigger watch values for candidate visibility and lane match fields.
  - R310 does not send Telegram, fetch account data, or submit orders.

### Existing Risk-Contract Readiness

- `src/app/hammer_radar/operator/expansion_risk_contract_preview_repair.py`
  - Existing exact lane risk-contract lookup and validation for the R306 expansion lane set.
  - R310 reuses `build_expansion_risk_contract_lane_preview`.
  - After R309 apply, baseline, primary, and secondary lanes resolve as exact valid contracts.
- `src/app/hammer_radar/operator/expansion_risk_contract_human_reviewed_write_gate.py`
  - Existing manual exact-phrase write gate. R310 does not import or call its write path.
- `src/app/hammer_radar/operator/tiny_live_risk_contract_validation.py`
  - Existing validation policy for risk-contract rows.

### Existing Final Command / Submit Boundaries

- `src/app/hammer_radar/operator/tiny_live_final_authorization_gate.py`
- `src/app/hammer_radar/operator/tiny_live_final_console.py`
  - Existing final authorization and cockpit surfaces still own final submit readiness.
  - R310 emits `submit_allowed=false`, `final_command_available=false`, `executable_payload_created=false`, and `signed_request_created=false`.

### Existing Inspect Commands

- `src/app/hammer_radar/operator/inspect.py`
  - Existing R306/R307/R309 inspect commands are present.
  - R310 adds `multi-lane-dry-run-observation` beside those commands.

### Existing Docs And Tests

- `docs/hammer_radar/live_readiness/R306_ELIGIBLE_LANE_EXPANSION_DRY_RUN_PREVIEW.md`
- `docs/hammer_radar/live_readiness/R309_HUMAN_REVIEWED_RISK_CONTRACT_WRITE_GATE.md`
- `tests/hammer_radar/test_eligible_lane_expansion_dry_run_preview.py`
- `tests/hammer_radar/test_expansion_risk_contract_human_reviewed_write_gate.py`
- `tests/hammer_radar/test_tiny_live_autonomous_trigger_scheduler.py`
- `tests/hammer_radar/test_tiny_live_fresh_trigger_watch.py`

## Duplicate Risks

- R306 already previews eligible expansion lanes, but it is not an observation scheduler tick and does not write the R310 ledger.
- R307 already repairs/previews risk-contract readiness, but it is contract-focused and not a timer/candidate observation packet.
- R288 already schedules the autonomous trigger loop, but it targets the existing one-lane trigger path. R310 records multi-lane observation only and does not call trigger-loop execution.
- R292 already checks timer health, so R310 consumes that packet instead of adding a new systemd parser.

## Selected Implementation Path

R310 creates `src/app/hammer_radar/operator/multi_lane_dry_run_observation_scheduler.py`.

The module:

- reuses R306/R307 lane sets
- reuses R307 exact risk-contract validation
- reuses R292 timer health
- reuses R286 fresh-trigger visibility
- writes only `logs/hammer_radar_forward/multi_lane_dry_run_observation.ndjson` on `--once`
- keeps `--preview` read-only
- exposes `inspect multi-lane-dry-run-observation`
- emits a gate matrix for the recommended R311 path

## Why R310 Does Not Enable Live Or Arm Lanes

R310 does not call arming modules, risk-contract write gates, final submit gates, Binance connectors, leverage/margin flows, or systemd mutation commands. Every packet includes:

```text
live_execution_enabled=false
allow_live_orders=false
global_kill_switch=true
order_placed=false
real_order_placed=false
execution_attempted=false
submit_allowed=false
final_command_available=false
real_order_forbidden=true
binance_order_endpoint_called=false
binance_test_order_endpoint_called=false
leverage_change_called=false
margin_change_called=false
secrets_shown=false
paper_live_separation_intact=true
autonomous_arming_state_changed=false
global_live_flags_changed=false
risk_contract_config_mutated=false
config_written=false
env_written=false
env_mutated=false
systemd_unit_mutated=false
scheduler_started=false
```
