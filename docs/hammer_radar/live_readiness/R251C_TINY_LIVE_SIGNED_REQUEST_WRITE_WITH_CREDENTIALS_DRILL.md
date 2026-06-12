# R251C Tiny-Live Signed Request Write With Credentials Drill

R251C wraps the existing R251 signed request write gate for the official tiny-live lane:

`BTCUSDT|8m|short|ladder_close_50_618`

## Scope

This phase consumes the latest R251B credential-presence drill record, confirms the current process still has `BINANCE_API_KEY` and `BINANCE_API_SECRET`, and then delegates the local signed request artifact write to R251 only after the exact R251C confirmation phrase.

R251C uses credentials only in memory through the R251 gate. It writes local artifacts only and never calls Binance, submits, places orders, mutates `.env`, mutates configs, changes lane controls, changes live flags, or disables the kill switch.

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-signed-request-with-credentials-drill
```

Rejected write example:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-signed-request-with-credentials-drill \
  --write-signed-request-with-credentials \
  --confirm-tiny-live-signed-request-with-credentials "wrong"
```

Confirmed local signed request artifact write:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-signed-request-with-credentials-drill \
  --write-signed-request-with-credentials \
  --confirm-tiny-live-signed-request-with-credentials "I CONFIRM TINY LIVE SIGNED REQUEST WITH CREDENTIALS DRILL ONLY; WRITE LOCAL SIGNED REQUEST ARTIFACT ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL."
```

## Ledgers

Confirmed writes append the R251 signed request artifact ledger:

`logs/hammer_radar_forward/tiny_live_signed_request_write_gate.ndjson`

Confirmed successful R251C wrapper runs also append:

`logs/hammer_radar_forward/tiny_live_signed_request_with_credentials_drill.ndjson`

Preview, bad-confirmation, missing R251B, missing environment credentials, R251-blocked, and secret-validation-blocked paths write no R251C wrapper ledger.

## Safety

R251C must keep:

- `submit_allowed=false`
- `binance_call_allowed=false`
- `network_allowed=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `binance_order_endpoint_called=false`
- `binance_test_order_endpoint_called=false`
- `secrets_shown=false`
- `secrets_persisted=false`
- `secret_values_in_output=false`
- env/config/lane controls unchanged
- official tiny-live lane unchanged
- kill switch not disabled

R251C is not a submit phase. R252 must consume the signed request artifact in preview-only mode, require a future read-only mark-price refresh before any later submit gate, and keep no Binance call, no submit, and no order placement.
