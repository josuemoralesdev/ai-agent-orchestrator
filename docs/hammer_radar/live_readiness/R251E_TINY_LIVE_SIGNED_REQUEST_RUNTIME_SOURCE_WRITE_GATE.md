# R251E Tiny-Live Signed Request Runtime Source Write Gate

R251E wraps the existing R251 signed request write gate for the official tiny-live lane:

`BTCUSDT|8m|short|ladder_close_50_618`

## Scope

This phase consumes the R251D runtime credential source resolver and uses credentials from:

- the current process environment, or
- `/home/josue/.config/hammer-radar/binance-signing.env`, or
- `HAMMER_BINANCE_SIGNING_ENV_FILE` when set to a valid absolute path outside the repo.

The external env file must be absolute, outside the repository, a regular file, and mode `0600` or otherwise inaccessible to group/world users. R251E reads credential values only in the exact confirmed write path, keeps them in memory, delegates local signing to R251, and then validates that raw credential values are absent from the R251 and R251E artifacts.

R251E does not call Binance, submit, place orders, mutate `.env`, mutate configs, change lane controls, write the external env file, change live flags, disable the kill switch, append paper outcomes, or promote strategies.

## Commands

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-signed-request-runtime-source-write-gate
```

Rejected write example:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-signed-request-runtime-source-write-gate \
  --write-signed-request-runtime-source \
  --confirm-tiny-live-signed-request-runtime-source-write "wrong"
```

Confirmed local signed request artifact write:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-signed-request-runtime-source-write-gate \
  --write-signed-request-runtime-source \
  --confirm-tiny-live-signed-request-runtime-source-write "I CONFIRM TINY LIVE SIGNED REQUEST RUNTIME SOURCE WRITE GATE ONLY; WRITE LOCAL SIGNED REQUEST ARTIFACT ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL."
```

## Ledgers

Confirmed successful writes append the R251 signed request artifact ledger:

`logs/hammer_radar_forward/tiny_live_signed_request_write_gate.ndjson`

Confirmed successful R251E wrapper runs also append:

`logs/hammer_radar_forward/tiny_live_signed_request_runtime_source_write_gate.ndjson`

Preview, bad-confirmation, missing/unsafe runtime credential source, R251-blocked, and secret-validation-blocked paths write no R251E wrapper ledger.

## Safety

R251E must keep:

- `signed_request_runtime_source_write_gate_only=true`
- `submit_allowed=false`
- `binance_call_allowed=false`
- `network_allowed=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `binance_order_endpoint_called=false`
- `binance_test_order_endpoint_called=false`
- `binance_account_endpoint_called=false`
- `binance_exchange_info_endpoint_called=false`
- `binance_mark_price_endpoint_called=false`
- `external_env_file_written=false`
- `secrets_shown=false`
- `secrets_persisted=false`
- `secret_values_in_output=false`
- env/config/lane controls unchanged
- official tiny-live lane unchanged
- kill switch not disabled

`hmac_signature_created`, `signed_request_written`, `signed_order_request_created`, and `signed_trading_request_created` may be true only after the exact R251E confirmation phrase and a ready runtime credential source.

R251E is not a submit phase. R252 must consume the runtime-source signed request artifact in preview-only mode, require a future read-only mark-price refresh before any later submit gate, and keep no Binance call, no submit, and no order placement.
