# R110 First-Live Readiness Burn-Down Pack

Phase: R110

Status: IMPLEMENTED

Classification:
- Primary: DIAGNOSTIC / AUDIT
- Secondary: WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## What R110 Adds

R110 adds a launch-readiness planner over the existing R102-R109 first-live surfaces:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward first-live-burn-down
```

The command returns JSON with:
- current R102/R104/R105/R106/R109 gate chain status
- blocker groups by candidate, approval records, environment flags, Binance credentials, account/funding, protective orders, adapter boundary, strategy quality, Telegram, confirmation phrase, and manual unknowns
- a prioritized tomorrow morning burn-down list
- copy-pasteable morning command pack
- human checklist
- readiness path from `BLOCKED` to future explicit execution authorization
- R111 prerequisite-clearing recommendation

R110 writes append-only evidence to:

```text
logs/hammer_radar_forward/first_live_burn_down_reports.ndjson
```

## What R110 Does Not Add

R110 does not add:
- live trading
- live env changes
- Binance order calls
- Binance account or balance calls
- approval-to-execution wiring
- Telegram-to-execution wiring
- a live order endpoint
- execution authority
- service restarts

It always reports:
- `live_ready=false`
- `execution_enabled_by_burn_down=false`
- `order_placed=false`
- `execution_attempted=false`
- `real_order_possible=false`
- `secrets_shown=false`

## Why This Replaced The Passive Overnight Watchdog

The R102-R109 wall of blockers is too broad for a fast morning push. A passive watchdog would only repeat that the system is blocked.

R110 instead turns the same existing evidence into an ordered burn-down:
1. identify the fresh candidate problem
2. verify preflight state
3. clear approval records
4. review environment and credential presence safely
5. confirm account/funding and protective readiness through future authorized checks
6. re-run the R106/R109 chain
7. keep the sacred button intent-only

This is planning and prioritization, not a new gate.

## How To Run The Burn-Down Command

Default log directory:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward first-live-burn-down
```

Explicit candidate:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward first-live-burn-down \
  --candidate-id 'normal|BTCUSDT|13m|long|ladder_close_50_618'
```

To inspect without writing the R110 ledger:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward first-live-burn-down --no-record
```

## How To Use The Morning Command Pack

Run the commands in the returned `morning_command_pack` in this order:
1. `final_live_preflight`
2. `tiny_live_armed_dry_run`
3. `one_tiny_live_order_protocol`
4. `first_live_activation_gate`
5. `approval_cockpit_state_curl`
6. `first_live_burn_down`

The curl command only reads the local approval cockpit state. Do not start, stop, restart, or expose services as part of R110.

## How Blockers Are Grouped

R110 groups existing blocker strings into:
- `candidate_blockers`
- `approval_record_blockers`
- `environment_flag_blockers`
- `binance_credential_blockers`
- `account_funding_blockers`
- `protective_order_blockers`
- `adapter_blockers`
- `strategy_quality_blockers`
- `telegram_blockers`
- `confirmation_phrase_blockers`
- `unknown_or_manual_check_blockers`

Each group includes blockers, count, owner, whether it can be cleared tomorrow, next action, verification command, and related phase.

## What Can Be Cleared Tomorrow

R111 should focus on prerequisite clearing:
- fresh promoted candidate identification
- R102 final preflight consistency
- final approval intent evidence
- human review records and hash matching
- Binance credential presence booleans without exposing values
- account/funding verification through an explicitly safe read-only procedure
- protective order readiness
- live adapter boundary review
- tiny position size and max loss cap records
- R109 sacred button intent-only review

## What Still Requires Future Explicit Authorization

The following still require a later phase with explicit authorization:
- live env flag changes
- live order placement
- Binance order endpoints
- account/balance/funding API calls if not separately authorized
- any approval-button-to-execution wiring
- any live order endpoint
- any execution phase after `FIRST_LIVE_ACTIVATION_READY`

R106 remains the activation gate authority. R109 remains intent-only.

## Safety Constraints

R110 preserves:
- no orders
- no live trading enablement
- no Binance order calls
- no env edits
- no exposed secrets
- no execution authority
- no approval-to-execution wiring
- paper/live separation

## How This Prepares R111

R110 creates the prioritized checklist and command pack that R111 can use to clear prerequisites. R111 should not place orders. It should convert the remaining R102-R109 blockers into auditable records and safe verification steps before any later explicit execution authorization phase is considered.
