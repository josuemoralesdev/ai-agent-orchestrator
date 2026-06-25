# R308 Expansion Risk Contract Write-Gate Preview

## Why R308 Exists

R307 proved that the current R306 baseline and expansion lanes are missing exact rows in:

```text
configs/hammer_radar/tiny_live_risk_contracts.json
```

R308 prepares the human review packet for those missing rows. It does not write config.

## What It Previews

R308 proposes preview-only risk-contract rows for:

- required baseline: `BTCUSDT|44m|long|ladder_close_50_618`
- primary dry-run expansion lanes:
  - `BTCUSDT|44m|short|ladder_382_50_618`
  - `BTCUSDT|44m|short|ladder_close_50_618`
  - `BTCUSDT|55m|long|ladder_close_50_618`
- secondary watch-only lanes:
  - `BTCUSDT|44m|short|ladder_22_44_22`
  - `BTCUSDT|44m|long|ladder_382_50_618`
  - `BTCUSDT|55m|long|market_close`
  - `BTCUSDT|88m|long|ladder_382_50_618`

Each proposed row uses the tiny-live explicit notional envelope:

```text
symbol=BTCUSDT
margin_mode=isolated
leverage=10
max_position_notional_usdt=80
margin_budget_usdt=8
max_trades_per_day=1
daily_loss_stop_usdt=5
protective_orders_required=true
live_execution_enabled=false
allow_live_orders=false
```

`max_loss_usdt` is derived only from `funding_config.max_loss_usdt` when it is present and inside the existing tiny-live max-loss cap. Otherwise the row is blocked with `risk_contract_max_loss_requires_operator_review`.

## How To Review

Run the module:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.expansion_risk_contract_write_gate_preview --log-dir logs/hammer_radar_forward
```

Use the inspect route:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward expansion-risk-contract-write-gate-preview
```

Use the operator text script:

```bash
bash scripts/hammer_print_r308_expansion_risk_contract_write_gate_preview.sh
```

Output ledger:

```text
logs/hammer_radar_forward/expansion_risk_contract_write_gate_preview.ndjson
```

Review:

- `proposed_contract_rows`
- `validation_preview`
- `missing_fields_after_preview`
- `diff_preview.would_add_lane_keys`
- `future_confirmation_phrase_preview`
- `recommended_r309_path`

## Why It Does Not Write

R308 has no active write confirmation phrase and no config apply function. The phrase:

```text
WRITE RISK CONTRACTS FOR R308 REVIEWED LANES
```

is preview-only. It is not executable in R308.

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
config_written=false
env_written=false
env_mutated=false
write_gate_preview_only=true
```

## What Not To Do

Do not copy these rows into config from R308. Do not arm expansion lanes. Do not change the first Tiny Live lane. Do not enable live execution, disable the kill switch, change leverage or margin, create a final command, submit an order, or call Binance order/test-order endpoints.

## Recommended R309 Paths

If all proposed rows are validation-ready and `max_loss_usdt` is resolved:

```text
R309 Human-Reviewed Risk Contract Write Gate
```

That future phase may write config only with an explicit operator confirmation phrase and must still keep live execution disabled.

If `max_loss_usdt` remains blocked:

```text
R309 Max Loss Derivation Review
```

Resolve the risk envelope before any write gate.
