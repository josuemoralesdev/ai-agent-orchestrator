# R254 Tiny-Live Submit Gate Preview

R254 consumes the latest R253B fresh-context regenerated artifacts for the official lane:

`BTCUSDT|8m|short|ladder_close_50_618`

R254 is a final preview before any actual tiny-live submit implementation. It validates the local signed request triplet and builds the future R255 submit gate requirements, but it does not submit, place orders, call Binance, read secrets, sign, write signed requests, mutate env/config/lane controls, or set `submit_allowed=true`.

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-submit-gate-preview
```

Rejected recording:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-submit-gate-preview \
  --record-submit-gate-preview \
  --confirm-tiny-live-submit-gate-preview "wrong"
```

Confirmed preview recording only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-submit-gate-preview \
  --record-submit-gate-preview \
  --confirm-tiny-live-submit-gate-preview "I CONFIRM TINY LIVE SUBMIT GATE PREVIEW RECORDING ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL."
```

## Inputs

R254 reads local artifacts only:

- latest R253B fresh-context signed request regeneration record
- latest R253B signed request artifact
- latest R253B executable payload artifact
- latest R253B stop/take-profit source artifact
- latest R253 final read-only mark-price refresh record
- latest R252 submit readiness preview record

The expected current R253B context is:

- main order: `SELL MARKET`, quantity `0.007`
- stop order: `BUY STOP_MARKET`, reduce-only, stop price `64309.3`, working type `MARK_PRICE`
- take-profit order: `BUY TAKE_PROFIT_MARKET`, reduce-only, stop price `62406.4`, working type `MARK_PRICE`
- reference price: `63675.0`
- estimated stop loss: about `4.4401 USDT`
- estimated reward: about `8.8802 USDT`
- risk/reward: about `2.0`

## Validation

R254 validates:

- R253B fresh regeneration exists and was written
- signed request artifact is created by `R253B_TINY_LIVE_FRESH_CONTEXT_SIGNED_REQUEST_REGENERATION_GATE`
- exactly three signed requests exist
- main/stop/take-profit signatures are present and 64 lowercase hex characters
- all signed requests target `POST /fapi/v1/order`
- main order shape is `SELL MARKET 0.007`
- stop order shape is `BUY STOP_MARKET reduceOnly=true stopPrice=64309.3 workingType=MARK_PRICE`
- take-profit order shape is `BUY TAKE_PROFIT_MARKET reduceOnly=true stopPrice=62406.4 workingType=MARK_PRICE`
- submit, network, order placement, and Binance order endpoint controls remain false

## Future R255 Phrase

R254 produces this metadata only. It must not execute it:

`I CONFIRM TINY LIVE BTCUSDT 8M SHORT SUBMIT ONLY; PLACE EXACTLY THREE BINANCE FUTURES ORDERS FROM LATEST R253B SIGNED REQUEST; MAIN SELL MARKET 0.007 BTC; STOP BUY STOP_MARKET REDUCE_ONLY; TAKE_PROFIT BUY TAKE_PROFIT_MARKET REDUCE_ONLY; NO OTHER ORDERS.`

R255 must still separately verify balances, current mark price, stale timestamp, signed request age, endpoint safety, idempotency, dedupe, kill-switch state, and order placement semantics.

## Ledger

Confirmed recordings append only:

`logs/hammer_radar_forward/tiny_live_submit_gate_preview.ndjson`

Preview, bad-confirmation, and validation-blocked paths write no R254 ledger.

## Safety

R254 must keep:

- `submit_gate_preview_only=true`
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
- `private_binance_endpoint_called=false`
- `signed_binance_endpoint_called=false`
- `network_allowed=false`
- `secrets_read=false`
- `secrets_shown=false`
- `secrets_persisted=false`
- `secret_values_in_output=false`
- `env_written=false`
- `env_mutated=false`
- `external_env_file_written=false`
- `config_written=false`
- `risk_contract_config_written=false`
- `lane_controls_written=false`
- `live_config_written=false`
- `kill_switch_disabled=false`
- `official_tiny_live_lane_changed=false`

## Next Phase

R255 should implement the actual tiny-live submit gate as a separate phase. It must require latest R254 preview, latest R253B signed request, exact operator confirmation, idempotency/dedupe, stale timestamp validation or regeneration, order endpoint allowlist, kill-switch check, post-submit reconciliation, and exactly three Binance Futures orders only if all gates pass.
