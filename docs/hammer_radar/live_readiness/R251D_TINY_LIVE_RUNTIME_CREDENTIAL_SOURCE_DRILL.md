# R251D Tiny-Live Runtime Credential Source Drill

R251D adds a repeatable runtime credential source resolver for the official tiny-live lane:

`BTCUSDT|8m|short|ladder_close_50_618`

## Scope

This phase checks whether Binance signing credentials are available from either:

- the current process environment
- `/home/josue/.config/hammer-radar/binance-signing.env`
- an override path set by `HAMMER_BINANCE_SIGNING_ENV_FILE`

The external env file must be outside this repository. R251D reads it only in memory for presence checks and path/permission validation.

R251D does not sign, create HMAC signatures, write signed request artifacts, call Binance/network endpoints, submit, place orders, mutate `.env`, mutate configs, change lane controls, write the external env file, change live flags, or disable the kill switch.

## Commands

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-runtime-credential-source-drill
```

Rejected recording example:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-runtime-credential-source-drill \
  --record-runtime-credential-source-drill \
  --confirm-tiny-live-runtime-credential-source-drill "wrong"
```

Confirmed presence-only recording:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-runtime-credential-source-drill \
  --record-runtime-credential-source-drill \
  --confirm-tiny-live-runtime-credential-source-drill "I CONFIRM TINY LIVE RUNTIME CREDENTIAL SOURCE DRILL RECORDING ONLY; NO SIGNING; NO ORDER; NO BINANCE CALL."
```

## External Env File

Expected operator-managed path:

`/home/josue/.config/hammer-radar/binance-signing.env`

Expected key names:

```text
BINANCE_API_KEY=<value>
BINANCE_API_SECRET=<value>
```

Do not create this file from Codex. Do not store it in Git. Do not paste, screenshot, log, or commit the credential values.

Safe manual setup expectations:

- create the file outside the repo
- keep the file owned by the current user
- set mode `0600`
- rerun R251D
- rerun R251C only after R251D reports a ready runtime source

## Ledger

Confirmed recordings append only:

`logs/hammer_radar_forward/tiny_live_runtime_credential_source_drill.ndjson`

Preview and bad-confirmation paths write no ledger.

## Safety

R251D must keep:

- `runtime_credential_source_drill_only=true`
- `signing_attempted=false`
- `hmac_signature_created=false`
- `signed_request_written=false`
- `signed_order_request_created=false`
- `submit_allowed=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `binance_order_endpoint_called=false`
- `binance_test_order_endpoint_called=false`
- `network_allowed=false`
- `external_env_file_written=false`
- `secrets_shown=false`
- `secrets_persisted=false`
- `secret_values_in_output=false`
- env/config/lane controls unchanged
- official tiny-live lane unchanged

R251D is a source-readiness drill only. It prepares future R251C/R252 wiring without signing, submitting, or placing an order.
