# R252 Tiny-Live Submit Readiness Preview

R252 adds a submit-readiness preview for the official tiny-live lane:

`BTCUSDT|8m|short|ladder_close_50_618`

## Scope

This phase reads local artifacts only:

- R251E runtime-source signed request write gate
- R251 signed request write gate
- R249 executable payload write gate
- R248 stop/take-profit source gate
- R242 Binance read-only precision/mark-price gate

It validates that the runtime-source signed request exists, the R251 signed request artifact has all three signed `/fapi/v1/order` requests, and all submit controls remain blocked. It then produces an operator packet that explains submit is not allowed yet.

R252 does not call Binance, submit, place orders, create test orders, sign, create HMAC signatures, write signed requests, read API keys, read API secrets, mutate `.env`, mutate external env files, mutate configs, mutate lane controls, disable the kill switch, append paper outcomes, update strategy performance, or promote any lane.

## Commands

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-submit-readiness-preview
```

Rejected recording example:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-submit-readiness-preview \
  --record-submit-readiness-preview \
  --confirm-tiny-live-submit-readiness-preview "wrong"
```

Confirmed preview recording:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-submit-readiness-preview \
  --record-submit-readiness-preview \
  --confirm-tiny-live-submit-readiness-preview "I CONFIRM TINY LIVE SUBMIT READINESS PREVIEW RECORDING ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL."
```

## Ledger

Confirmed recordings append only:

`logs/hammer_radar_forward/tiny_live_submit_readiness_preview.ndjson`

Preview, bad-confirmation, and validation-blocked paths write no R252 ledger.

## Current Readiness Result

The current local artifact chain represents:

- main order: `SELL MARKET` quantity `0.007`
- stop order: `BUY STOP_MARKET`, reduce-only, stop price `62844.6`
- take-profit order: `BUY TAKE_PROFIT_MARKET`, reduce-only, stop price `60941.7`
- reference price: `62210.3`
- estimated stop loss: `4.4401 USDT`
- estimated reward: `8.8802 USDT`
- risk/reward ratio: `2.0`
- max loss: `4.44 USDT`

Submit remains blocked:

- `submit_allowed=false`
- `network_allowed=false`
- `binance_call_allowed=false`
- `order_placed=false`

## Required Next Phase

R242 is now an older read-only mark-price/precision reference. R248/R249/R251 depend on that older context. Before any submit gate, a future R253 gate must refresh public read-only Binance mark price and exchange precision, then reconcile the fresh context against the signed request artifact.

Required future phase:

`R253_TINY_LIVE_FINAL_READONLY_MARK_PRICE_REFRESH_GATE`

R253 must refresh:

- mark price
- exchange info precision
- min notional
- quantity step validation
- stop/take-profit direction validation
- notional after rounding

R253 must still avoid order endpoints, private endpoints, signing, submit, and order placement.

## Safety

R252 must keep:

- `submit_readiness_preview_only=true`
- `hmac_signature_created=false`
- `signed_request_written=false`
- `signed_order_request_created=false`
- `signed_trading_request_created=false`
- `submit_allowed=false`
- `submit_attempted=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `binance_order_endpoint_called=false`
- `binance_test_order_endpoint_called=false`
- `binance_account_endpoint_called=false`
- `binance_exchange_info_endpoint_called=false`
- `binance_mark_price_endpoint_called=false`
- `network_allowed=false`
- `env_written=false`
- `env_mutated=false`
- `external_env_file_written=false`
- `config_written=false`
- `risk_contract_config_written=false`
- `lane_controls_written=false`
- `live_config_written=false`
- `secrets_shown=false`
- `secrets_persisted=false`
- `secret_values_in_output=false`
- `official_tiny_live_lane_changed=false`
