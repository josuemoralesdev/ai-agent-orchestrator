# R309 Human-Reviewed Risk Contract Write Gate

## Why R309 Exists

R308 produced a preview-only packet for eight missing exact risk-contract rows:

- `BTCUSDT|44m|long|ladder_close_50_618`
- `BTCUSDT|44m|short|ladder_382_50_618`
- `BTCUSDT|44m|short|ladder_close_50_618`
- `BTCUSDT|55m|long|ladder_close_50_618`
- `BTCUSDT|44m|short|ladder_22_44_22`
- `BTCUSDT|44m|long|ladder_382_50_618`
- `BTCUSDT|55m|long|market_close`
- `BTCUSDT|88m|long|ladder_382_50_618`

R309 adds the human-reviewed write gate for those exact R308-reviewed rows. The default behavior remains preview-only and does not write config.

## Exact Phrase

```text
WRITE RISK CONTRACTS FOR R308 REVIEWED LANES
```

The phrase must match exactly and must be paired with `--apply`.

## Default Preview Behavior

Run:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.expansion_risk_contract_human_reviewed_write_gate --log-dir logs/hammer_radar_forward
```

Default output:

- `preview_only=true`
- `apply_requested=false`
- `confirmation_phrase_matched=false`
- `config_written=false`
- `risk_contract_config_mutated=false`
- `would_add_lane_keys` lists missing exact rows

Inspect route:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward expansion-risk-contract-human-reviewed-write-gate
```

Operator script:

```bash
bash scripts/hammer_print_r309_expansion_risk_contract_human_reviewed_write_gate.sh
```

Ledger:

```text
logs/hammer_radar_forward/expansion_risk_contract_human_reviewed_write_gate.ndjson
```

## Apply Behavior

Manual apply command shape:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.expansion_risk_contract_human_reviewed_write_gate \
  --log-dir logs/hammer_radar_forward \
  --apply \
  --confirmation "WRITE RISK CONTRACTS FOR R308 REVIEWED LANES"
```

Apply mode:

- requires `--apply`
- requires the exact phrase
- validates every proposed row before writing
- skips already-existing exact lane keys
- appends missing exact rows only
- does not modify existing rows
- does not delete existing rows
- reloads config after write and validates added rows
- emits `config_sha256_before` and `config_sha256_after`

## Backup Behavior

Before any apply write, R309 creates a timestamped backup beside the target config:

```text
configs/hammer_radar/tiny_live_risk_contracts.json.r309_backup_<timestamp>
```

The write itself uses a temporary file in the same directory and atomic replace.

## Verify After Write

After a manual operator apply, verify:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward expansion-risk-contract-human-reviewed-write-gate
git diff -- configs/hammer_radar/tiny_live_risk_contracts.json configs/hammer_radar/autonomous_arming_state.json
```

Then confirm the final console still forbids real orders:

```bash
curl -s http://127.0.0.1:8015/tiny-live/final-console | jq '.final_tiny_live_authorization_gate_panel | {status, blockers, real_order_forbidden, submit_allowed, final_command_available, current_real_candidate_lane_key, armed: .exact_lane_armed_state, timer: {timer_active: .readiness_matrix.timer_active, timer_health_status: .readiness_matrix.timer_health_status}}'
```

## Why This Still Does Not Enable Live

R309 only appends local risk-contract rows. It keeps every new row at:

```text
live_execution_enabled=false
allow_live_orders=false
```

Every output also keeps:

```text
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
env_written=false
env_mutated=false
```

R309 does not arm lanes, change the first Tiny Live lane, generate final commands, submit orders, call Binance, change leverage, change margin, disable kill switches, or mutate live flags.

## What Not To Do

Do not run apply from automation. Do not run apply without reviewing the R308 and R309 output. Do not arm expansion lanes from this phase. Do not enable live execution, disable the kill switch, create a final command, submit, or call Binance order/test-order endpoints.

## Recommended R310 Paths

If the operator has not applied the write:

```text
R310 Operator Review And Apply Risk Contracts
```

This should remain a manual operator decision step.

If the operator applies and verifies risk contracts:

```text
R310 Multi-Lane Dry-Run Observation Scheduler
```

Observe baseline plus primary lanes in dry-run only, with no live execution and no arming mutation.
