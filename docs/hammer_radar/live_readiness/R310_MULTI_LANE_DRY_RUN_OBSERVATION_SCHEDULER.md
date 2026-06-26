# R310 Multi-Lane Dry-Run Observation Scheduler

## Why R310 Exists

R309 was manually applied by the operator with the exact confirmation phrase:

```text
WRITE RISK CONTRACTS FOR R308 REVIEWED LANES
```

That added the eight R308-reviewed risk-contract rows while preserving:

```text
live_execution_enabled=false
allow_live_orders=false
```

R310 uses those reviewed contracts to observe the baseline lane and primary expansion lanes in dry-run only.

## What R309 Changed

The following exact lane contracts now exist:

- `BTCUSDT|44m|long|ladder_close_50_618`
- `BTCUSDT|44m|short|ladder_382_50_618`
- `BTCUSDT|44m|short|ladder_close_50_618`
- `BTCUSDT|55m|long|ladder_close_50_618`
- `BTCUSDT|44m|short|ladder_22_44_22`
- `BTCUSDT|44m|long|ladder_382_50_618`
- `BTCUSDT|55m|long|market_close`
- `BTCUSDT|88m|long|ladder_382_50_618`

Each R309 row keeps `max_loss_usdt=4.44`, `margin_budget_usdt=8`, `leverage=10`, and `max_position_notional_usdt=80`.

## What Multi-Lane Dry-Run Observation Means

R310 records an observation packet for:

Baseline lane:

```text
BTCUSDT|44m|long|ladder_close_50_618
```

Primary dry-run observation lanes:

- `BTCUSDT|44m|short|ladder_382_50_618`
- `BTCUSDT|44m|short|ladder_close_50_618`
- `BTCUSDT|55m|long|ladder_close_50_618`

Secondary watch-only visible lanes:

- `BTCUSDT|44m|short|ladder_22_44_22`
- `BTCUSDT|44m|long|ladder_382_50_618`
- `BTCUSDT|55m|long|market_close`
- `BTCUSDT|88m|long|ladder_382_50_618`

The packet includes risk-contract readiness, current candidate visibility, timer health, lane role, observation status, observation action, and the R311 recommendation.

## What It Does Not Mean

R310 does not:

- enable live execution
- disable the kill switch
- arm or disarm lanes
- change the first Tiny Live lane
- write risk contracts
- write config
- write env files
- mutate systemd units
- start timers
- create final commands
- create executable payloads
- create signed requests
- submit orders
- call Binance order or test-order endpoints
- change leverage or margin
- print secrets

Betrayal/inverse remains lab-only and blocked from observed lanes.

## How To Run

Preview only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.multi_lane_dry_run_observation_scheduler --log-dir logs/hammer_radar_forward --preview
```

One-shot observation tick:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.multi_lane_dry_run_observation_scheduler --log-dir logs/hammer_radar_forward --once
```

Inspect route:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward multi-lane-dry-run-observation
```

Operator script:

```bash
bash scripts/hammer_print_r310_multi_lane_dry_run_observation.sh
```

Output ledger:

```text
logs/hammer_radar_forward/multi_lane_dry_run_observation.ndjson
```

## How To Read Output

- `lane_packets`: one row per baseline, primary, and secondary lane.
- `lane_role`: `BASELINE_CURRENT_FIRST_TINY_LIVE`, `PRIMARY_DRY_RUN_OBSERVATION`, or `SECONDARY_WATCH_ONLY_VISIBLE`.
- `observation_status`: `OBSERVING_DRY_RUN`, `WATCH_ONLY_VISIBLE`, `BLOCKED_RISK_CONTRACT`, `BLOCKED_TIMER_HEALTH`, or `BLOCKED_POLICY`.
- `observation_action`: `RECORD_ONLY_NO_SUBMIT`, `WATCH_ONLY_NO_SUBMIT`, or `BLOCKED_NO_ACTION`.
- `multi_lane_observation_gate_matrix`: baseline preservation, lane counts, risk-contract readiness, timer health, and R311 recommendation.

Every output keeps the required safety fields locked:

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

## Why It Still Does Not Arm Or Trade

R310 is an observation surface. It only reads existing readiness surfaces and appends an observation ledger on `--once`. It never calls the arming write path, final submit gate, Binance connector, leverage/margin readiness mutation, R309 write gate, or systemd mutation commands.

## Recommended R311 Paths

If R310 is clean:

```text
R311 Multi-Lane Dry-Run Timer Unit Preview
```

That phase should prepare, but not install or enable, a systemd timer/unit design for recurring multi-lane dry-run observation.

If R310 shows blockers:

```text
R311 Observation Blocker Repair
```
