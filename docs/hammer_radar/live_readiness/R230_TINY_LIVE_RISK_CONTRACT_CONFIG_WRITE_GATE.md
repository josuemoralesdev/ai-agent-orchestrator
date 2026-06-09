# R230 Tiny Live Risk Contract Config Write Gate

R230 consumes the latest recorded R229 preview for the official protected lane:

`BTCUSDT|8m|short|ladder_close_50_618`

It previews and, only with the exact confirmation phrase, writes the bounded local risk-contract entry to:

`configs/hammer_radar/tiny_live_risk_contracts.json`

This phase does not enable live execution, arm a lane, create order payloads, call Binance/network, disable the kill switch, mutate env, or write lane/fisherman/scheduler/live config.

## Commands

Preview only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-risk-contract-config-write-gate
```

Rejected confirmation:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-risk-contract-config-write-gate \
  --write-risk-config \
  --confirm-tiny-live-risk-contract-config-write "wrong"
```

Confirmed config write:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-risk-contract-config-write-gate \
  --write-risk-config \
  --confirm-tiny-live-risk-contract-config-write "I CONFIRM TINY LIVE RISK CONTRACT CONFIG WRITE ONLY; NO LIVE ENABLE; NO ORDER; NO BINANCE CALL."
```

## Inputs

R230 reads local surfaces only:

- `logs/hammer_radar_forward/tiny_live_risk_contract_preview.ndjson`
- `configs/hammer_radar/tiny_live_risk_contracts.json`

The append-only R230 audit ledger is:

```text
logs/hammer_radar_forward/tiny_live_risk_contract_config_write_gate.ndjson
```

## Write Rules

The config write is allowed only when:

- the latest R229 preview exists
- R229 still targets `BTCUSDT|8m|short|ladder_close_50_618`
- R229 status is `TINY_LIVE_RISK_CONTRACT_PREVIEW_READY` or `TINY_LIVE_RISK_CONTRACT_PREVIEW_RECORDED`
- R229 overall status is `TINY_LIVE_RISK_PREVIEW_READY_CONFIG_WRITE_REQUIRED_LATER`
- the proposed config entry validates
- `--write-risk-config` is present
- the exact R230 confirmation phrase is present

The write preserves existing config shape. The current repo config uses `risk_contracts` as a list, so R230 appends or updates only the official lane entry in that list and preserves existing contracts.

## Written Contract State

The official-lane contract remains not live-authorized:

- `approval_status=CONFIG_WRITTEN_NOT_LIVE_AUTHORIZED`
- `live_authorized=false`
- `live_execution_enabled=false`
- `enabled_for_preflight=false`
- `approved=false`
- `order_payload_forbidden_until_live_gate=true`
- `binance_call_forbidden_until_live_gate=true`

## Safety

R230 keeps:

- `lane_controls_written=false`
- `env_mutated=false`
- `live_config_written=false`
- `global_live_flags_changed=false`
- `kill_switch_disabled=false`
- `live_authorization_created=false`
- `live_execution_enabled=false`
- `order_payload_created=false`
- `executable_payload_created=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `binance_order_endpoint_called=false`
- `binance_test_order_endpoint_called=false`
- `network_allowed=false`
- `transfer_endpoint_called=false`
- `withdraw_endpoint_called=false`
- `official_tiny_live_lane_changed=false`

Only a confirmed write may set:

- `config_written=true`
- `risk_contract_config_written=true`

Those flags mean the local risk-contract config entry was written. They do not imply live authorization.

## Follow-Up

R231 should consume the written R230 config and preview live authorization requirements only. It must not enable live execution, call Binance/network, place orders, arm the lane, disable the kill switch, or create an order payload.
