# R244 Tiny-Live Leverage / Notional Risk Contract Write Gate

R244 consumes the recorded R243 leverage/notional adjustment preview for the official lane:

`BTCUSDT|8m|short|ladder_close_50_618`

It previews and, only with the exact confirmation phrase, writes the adjusted local risk-contract entry to:

`configs/hammer_radar/tiny_live_risk_contracts.json`

The adjusted contract models `44 USDT` as margin budget, `10x` leverage, and `440 USDT` max notional. This phase does not call Binance/network, create executable payloads, sign requests, place orders, mutate env, mutate `lane_controls.json`, enable live execution, or disable the kill switch.

## Commands

Preview only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-leverage-notional-risk-contract-write-gate
```

Rejected confirmation:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-leverage-notional-risk-contract-write-gate \
  --write-risk-contract \
  --confirm-tiny-live-leverage-notional-risk-contract-write "wrong"
```

Confirmed config write:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-leverage-notional-risk-contract-write-gate \
  --write-risk-contract \
  --confirm-tiny-live-leverage-notional-risk-contract-write "I CONFIRM TINY LIVE LEVERAGE NOTIONAL RISK CONTRACT WRITE GATE ONLY; WRITE RISK CONFIG ONLY; NO ORDER; NO BINANCE CALL."
```

Audit ledger:

`logs/hammer_radar_forward/tiny_live_leverage_notional_risk_contract_write_gate.ndjson`

## Write Rules

R244 writes only when:

- the latest R243 adjustment preview is recorded
- R243 says the adjusted model clears Binance minimums
- the adjusted contract validates for the official lane
- `--write-risk-contract` is present
- the exact R244 confirmation phrase is present

The write preserves the existing config shape and updates only the official lane contract.

## Written Contract State

The official-lane contract remains not live-authorized:

- `capital_mode=tiny_live_margin_10x`
- `margin_budget_usdt=44`
- `tiny_live_margin_usdt=44`
- `leverage=10`
- `max_notional_usdt=440`
- `max_position_notional_usdt=440`
- `max_loss_requires_review=true`
- `approval_status=CONFIG_WRITTEN_NOT_LIVE_AUTHORIZED`
- `live_authorized=false`
- `live_execution_enabled=false`
- `enabled_for_preflight=false`
- `order_payload_forbidden_until_live_gate=true`
- `binance_call_forbidden_until_live_gate=true`

## Safety

R244 keeps:

- `env_mutated=false`
- `lane_controls_written=false`
- `live_config_written=false`
- `order_payload_created=false`
- `executable_payload_created=false`
- `signed_order_request_created=false`
- `signed_trading_request_created=false`
- `signed_readonly_request_created=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `binance_order_endpoint_called=false`
- `binance_test_order_endpoint_called=false`
- `binance_account_endpoint_called=false`
- `binance_exchange_info_endpoint_called=false`
- `binance_mark_price_endpoint_called=false`
- `network_allowed=false`
- `kill_switch_disabled=false`
- `official_tiny_live_lane_changed=false`

Only a confirmed write may set:

- `config_written=true`
- `risk_contract_config_written=true`

Those flags mean the local risk-contract config entry was written. They do not imply live authorization or order readiness.

## Follow-Up

R245 should refresh the non-executable order payload preview using the R244 `10x / 440 USDT` risk contract and the latest R242 read-only precision/mark-price result. It must not create an executable payload, sign a request, call Binance order endpoints, or place an order.
