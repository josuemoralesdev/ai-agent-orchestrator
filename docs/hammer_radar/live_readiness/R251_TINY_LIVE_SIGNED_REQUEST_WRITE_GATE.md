# R251 Tiny-Live Signed Request Write Gate

R251 adds a controlled local signed request artifact write gate for the official tiny-live lane:

`BTCUSDT|8m|short|ladder_close_50_618`

## Scope

This phase consumes the latest R250 signature gate preview and R249 executable payload artifact, validates that the payload remains official-lane and unsubmitted, and builds canonical Binance Futures `/fapi/v1/order` request query strings for:

- `main_order`
- `stop_order`
- `take_profit_order`

Preview mode does not read credential values, does not sign, and does not write a ledger.

Confirmed write mode requires the exact R251 confirmation phrase and present `BINANCE_API_KEY` / `BINANCE_API_SECRET` environment variables. The credentials are used only in memory to create HMAC SHA256 signatures. The local artifact stores signatures and canonical query strings, but not API secrets or raw API keys.

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-signed-request-write-gate
```

Rejected write example:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-signed-request-write-gate \
  --write-signed-request \
  --confirm-tiny-live-signed-request-write "wrong"
```

Confirmed local artifact write:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-signed-request-write-gate \
  --write-signed-request \
  --confirm-tiny-live-signed-request-write "I CONFIRM TINY LIVE SIGNED REQUEST WRITE GATE ONLY; WRITE LOCAL SIGNED REQUEST ARTIFACT ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL."
```

## Ledger

Confirmed writes append only:

`logs/hammer_radar_forward/tiny_live_signed_request_write_gate.ndjson`

No ledger is written during preview, bad confirmation, missing credential, or validation-blocked paths.

## Safety

R251 must keep:

- `submit_allowed=false`
- `binance_call_allowed=false`
- `network_allowed=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `binance_order_endpoint_called=false`
- `secrets_shown=false`
- `secrets_persisted=false`
- kill switch not disabled
- env/config/lane controls not mutated

R251 is not a submit phase. R252 must remain preview-only and require a future read-only mark-price refresh before any later submit gate.
