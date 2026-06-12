# R253B Tiny-Live Fresh Context Signed Request Regeneration Gate

R253B consumes the latest R253 final read-only mark-price refresh for the official lane:

`BTCUSDT|8m|short|ladder_close_50_618`

R253 showed the old signed request was stale because the fresh mark price moved above the old short stop. R253B regenerates local artifacts from the recorded R253 context only:

- stop/take-profit source
- executable payload
- signed request artifact
- R253B wrapper audit record

R253B does not submit, place orders, call Binance, refresh public market data, call private/signed endpoints, mutate env/config/lane controls, or disable the kill switch.

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-fresh-context-signed-request-regeneration-gate
```

Rejected write attempt:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-fresh-context-signed-request-regeneration-gate \
  --regenerate-fresh-context-signed-request \
  --confirm-tiny-live-fresh-context-regeneration "wrong"
```

Confirmed local regeneration only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-fresh-context-signed-request-regeneration-gate \
  --regenerate-fresh-context-signed-request \
  --confirm-tiny-live-fresh-context-regeneration "I CONFIRM TINY LIVE FRESH CONTEXT SIGNED REQUEST REGENERATION ONLY; NO SUBMIT; NO ORDER; NO BINANCE ORDER CALL."
```

## Regeneration Rules

R253B requires the latest R253 record to show:

- `must_regenerate_signed_request_before_submit=true`
- `fresh_context_compatible_with_signed_artifact=false`
- `submit_gate_preview_allowed_next=false`
- `submit_allowed=false`
- `order_placed=false`

The fresh R253 mark becomes the new `reference_price`. For the official short lane:

- stop is rebuilt above the fresh mark
- take profit is rebuilt below the fresh mark
- quantity remains `0.007 BTC`
- max-loss target remains near `4.44 USDT`
- reward/risk target remains near `2.0`
- tick size, step size, and min notional are validated from the recorded R253 context

The configured risk contract is read only. R253B does not write risk config.

## Artifact Writes

After exact confirmation and successful validation, R253B appends:

- `logs/hammer_radar_forward/tiny_live_stop_take_profit_source_gate.ndjson`
- `logs/hammer_radar_forward/tiny_live_executable_payload_write_gate.ndjson`
- `logs/hammer_radar_forward/tiny_live_signed_request_write_gate.ndjson`
- `logs/hammer_radar_forward/tiny_live_fresh_context_signed_request_regeneration_gate.ndjson`

Each appended artifact identifies `R253B_TINY_LIVE_FRESH_CONTEXT_SIGNED_REQUEST_REGENERATION_GATE` as the creator/source phase.

## Safety

R253B preserves:

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
- `secrets_shown=false`
- `secrets_persisted=false`
- `secret_values_in_output=false`
- `paper_live_separation_intact=true`

HMAC signatures are created only after the exact R253B confirmation phrase and only in memory using the runtime credential source. Raw API keys and secrets are not written to artifacts.

## Next Phase

R254 should consume the R253B regenerated signed request plus the R253 final read-only refresh and preview the final submit gate only. R254 must still keep `submit_allowed=false`, avoid Binance order calls, avoid submit/order placement, and prepare an exact future submit confirmation phrase for a separate final submit/write gate.
