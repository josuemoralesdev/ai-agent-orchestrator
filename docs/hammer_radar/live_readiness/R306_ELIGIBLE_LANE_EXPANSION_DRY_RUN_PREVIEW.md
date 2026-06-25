# R306 Eligible Lane Expansion Dry-Run Preview

## Why R306 Exists

R304 made paper refresh durable and added the Strategy Lab preview. R305 added a Strategy Lab Variant Test Pack and ranked direct-evidence variants without changing Tiny Live safety. R306 turns the R305 recommendation into a read-only operator preview for controlled dry-run expansion candidates.

The current first Tiny Live lane remains:

```text
BTCUSDT|44m|long|ladder_close_50_618
```

## What Dry-Run Expansion Means

Dry-run expansion means observing additional lanes in a future scheduler phase while keeping live execution disabled. R306 identifies primary dry-run expansion candidates, secondary watch-only candidates, required gates, risk-contract preview status, timer requirements, and blockers preventing live execution.

Primary dry-run expansion candidates:

- `BTCUSDT|44m|short|ladder_382_50_618`
- `BTCUSDT|44m|short|ladder_close_50_618`
- `BTCUSDT|55m|long|ladder_close_50_618`

Secondary watch-only candidates:

- `BTCUSDT|44m|short|ladder_22_44_22`
- `BTCUSDT|44m|long|ladder_382_50_618`
- `BTCUSDT|55m|long|market_close`
- `BTCUSDT|88m|long|ladder_382_50_618`

## What It Does Not Mean

R306 is not live expansion. It does not:

- enable live execution
- disable the kill switch
- arm or disarm lanes
- change the first Tiny Live lane
- write risk contracts
- create final commands
- create executable order payloads
- call Binance order or test-order endpoints
- change leverage or margin
- print secrets
- allow submit

Betrayal/inverse remains lab-only and capture-only.

## How To Run

Direct module:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.eligible_lane_expansion_dry_run_preview --log-dir logs/hammer_radar_forward
```

Inspect route:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward eligible-lane-expansion-dry-run-preview
```

Operator text script:

```bash
bash scripts/hammer_print_r306_eligible_lane_expansion_preview.sh
```

Output ledger:

```text
logs/hammer_radar_forward/eligible_lane_expansion_dry_run_preview.ndjson
```

## How To Read Output

- `lane_packets`: one row per baseline, primary, and secondary lane.
- `lane_role`: distinguishes baseline, primary dry-run candidate, secondary watch-only, and rejected policy.
- `expansion_preview_status`: `BASELINE_UNCHANGED`, `DRY_RUN_PREVIEW_ELIGIBLE`, `WATCH_ONLY`, or `BLOCKED`.
- `exact_risk_contract_preview`: exact lane risk-contract presence, validity, and blockers.
- `timer_requirement`: requires active dry-run scheduler timer health in a later observation phase.
- `current_candidate_status`: current fresh/real candidate match status.
- `expansion_gate_matrix`: final high-level decision matrix and recommended next operator move.

Every output keeps:

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
risk_contract_config_mutated=false
global_live_flags_changed=false
```

## What Not To Do

Do not use R306 output as live approval. Do not enable live flags, submit orders, create signed requests, change leverage or margin, mutate risk contracts, or add primary expansion lanes to arming state from this phase.

## R307 Recommendation

If R306 is clean and exact preview requirements are acceptable:

```text
R307 Multi-Lane Dry-Run Observation Scheduler
```

It should observe baseline plus primary dry-run expansion lanes without enabling live, without changing the current first live lane, and without final submit.

If R306 reveals missing risk contracts or incomplete gating:

```text
R307 Expansion Risk Contract Preview Repair
```

It should preview missing lane risk contracts without writing config or enabling live.
