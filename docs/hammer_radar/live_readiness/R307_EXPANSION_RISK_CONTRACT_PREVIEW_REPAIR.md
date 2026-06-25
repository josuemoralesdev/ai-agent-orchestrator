# R307 Expansion Risk Contract Preview Repair

## Why R307 Exists

R306 created a read-only eligible lane expansion dry-run preview. It preserved the first Tiny Live lane and all live safety flags, but its risk-contract preview did not clearly distinguish a missing exact lane row from a validation failure on an empty match.

R307 repairs that preview path.

## What R306 Exposed

The current first Tiny Live lane remains:

```text
BTCUSDT|44m|long|ladder_close_50_618
```

R306 also inspected primary expansion lanes:

- `BTCUSDT|44m|short|ladder_382_50_618`
- `BTCUSDT|44m|short|ladder_close_50_618`
- `BTCUSDT|55m|long|ladder_close_50_618`

The current risk-contract config contains a 13m older candidate row and an 8m official lane row. It does not contain exact 44m/55m rows for the R306 lanes, so the repaired preview reports missing exact contracts and emits preview-only templates.

## How The Resolver Works

Run:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.expansion_risk_contract_preview_repair --log-dir logs/hammer_radar_forward
```

Inspect route:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward expansion-risk-contract-preview-repair
```

Operator text:

```bash
bash scripts/hammer_print_r307_expansion_risk_contract_preview_repair.sh
```

Output ledger:

```text
logs/hammer_radar_forward/expansion_risk_contract_preview_repair.ndjson
```

For each lane, the resolver normalizes:

```text
symbol|timeframe|direction|entry_mode
```

It attempts to match:

- `official_lane_key`
- `lane_key`
- derived `symbol|timeframe|direction|entry_mode`

Matched contracts are validated with the existing tiny-live risk-contract validation helper.

## Matched Contracts Versus Preview Templates

If `exact_contract_found=true`, the row includes:

- `matched_contract_key`
- `matched_contract_schema_version`
- `validation_summary`
- non-sensitive risk values

If `exact_contract_found=false`, the row includes:

- `lookup_attempts`
- `lookup_failure_reason`
- `safe_preview_template_if_missing`
- `safe_preview_template_status=PREVIEW_TEMPLATE_AVAILABLE_NOT_WRITTEN`
- `future_write_gate_required=true`

The preview template uses:

- `leverage=10`
- `margin_mode=isolated`
- `max_position_notional_usdt=80`
- `margin_budget_usdt=8`
- `max_trades_per_day=1`
- `daily_loss_stop_usdt=5`
- `protective_orders_required=true`

`max_loss_usdt` remains `null` in missing templates and is blocked by `risk_contract_max_loss_requires_operator_review`.

## What Not To Do

Do not use R307 output as live approval. Do not write the templates to config from this phase. Do not arm expansion lanes, disable the kill switch, enable live execution, change leverage or margin, create final commands, submit orders, or call Binance order/test-order endpoints.

## Why No Config Is Written

R307 is preview-only. It has no write confirmation phrase and no apply function. Every output keeps:

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
config_written=false
env_written=false
env_mutated=false
```

## Recommended R308 Paths

If missing contracts remain:

```text
R308 Expansion Risk Contract Write-Gate Preview
```

This should still not write config. It should produce a human-reviewed write gate packet only.

If all necessary contracts resolve:

```text
R308 Multi-Lane Dry-Run Observation Scheduler
```

This should observe baseline plus primary lanes in dry-run only, with no live execution and no arming mutation.
