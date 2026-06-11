# R251B Tiny-Live Signing Credential Presence Drill

R251B adds a presence-only credential drill for the official tiny-live lane:

`BTCUSDT|8m|short|ladder_close_50_618`

## Scope

This phase checks only whether `BINANCE_API_KEY` and `BINANCE_API_SECRET` exist in the current process environment.

It does not read credential values for signing, print credential values, persist credential values, create HMAC signatures, write signed request artifacts, call Binance/network endpoints, submit, place orders, mutate `.env`, mutate configs, change lane controls, or disable the kill switch.

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-signing-credential-presence-drill
```

Rejected recording example:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-signing-credential-presence-drill \
  --record-signing-credential-presence-drill \
  --confirm-tiny-live-signing-credential-presence-drill "wrong"
```

Confirmed presence-only recording:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-signing-credential-presence-drill \
  --record-signing-credential-presence-drill \
  --confirm-tiny-live-signing-credential-presence-drill "I CONFIRM TINY LIVE SIGNING CREDENTIAL PRESENCE DRILL RECORDING ONLY; NO SIGNING; NO ORDER; NO BINANCE CALL."
```

## Ledger

Confirmed recordings append only:

`logs/hammer_radar_forward/tiny_live_signing_credential_presence_drill.ndjson`

Preview and bad-confirmation paths write no ledger.

## Operator Credential Guidance

- Set credentials in the shell/session or service environment outside Git.
- Do not paste secrets into chat, commits, logs, task files, or docs.
- Do not write `.env` from this phase.
- After credentials are present, rerun the R251 signed request write gate with the exact R251 confirmation phrase.

## Safety

R251B must keep:

- `credential_presence_drill_only=true`
- `signing_attempted=false`
- `hmac_signature_created=false`
- `signed_request_written=false`
- `signed_order_request_created=false`
- `submit_allowed=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `binance_order_endpoint_called=false`
- `network_allowed=false`
- `secrets_shown=false`
- `secrets_persisted=false`
- `secret_values_in_output=false`
- env/config/lane controls unchanged

R251B is not a signing phase. R251C should rerun the existing R251 signed request write gate only after credentials are present, still with no Binance call, submit, or order placement.
