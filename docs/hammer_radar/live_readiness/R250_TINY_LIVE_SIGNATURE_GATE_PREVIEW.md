# R250 Tiny-Live Signature Gate Preview

R250 adds a preview-only signature gate for the official lane:

`BTCUSDT|8m|short|ladder_close_50_618`

The gate consumes the latest recorded R249 executable payload artifact and builds unsigned Binance Futures request templates for later review. It does not sign, write signed requests, call Binance, submit, place orders, mutate env/config/lane controls, or disable the kill switch.

## Safety State

- Preview is default.
- Optional confirmed mutation is limited to `logs/hammer_radar_forward/tiny_live_signature_gate_preview.ndjson`.
- The exact confirmation phrase is `I CONFIRM TINY LIVE SIGNATURE GATE PREVIEW RECORDING ONLY; NO SIGNED REQUEST; NO ORDER; NO BINANCE CALL.`
- The preview uses placeholder labels only: `timestamp=<FUTURE_TIMESTAMP>` and `signature=<NOT_CREATED>`.
- `api_key_loaded=false`.
- `api_secret_loaded=false`.
- `secrets_read=false`.
- `secrets_shown=false`.
- `hmac_signature_created=false`.
- `signed_request_written=false`.
- `signed_order_request_created=false`.
- `submit_allowed=false`.
- `binance_call_allowed=false`.
- `network_allowed=false`.
- `order_placed=false`.

## Validation

R250 requires:

- latest R249 executable payload artifact exists for `BTCUSDT|8m|short|ladder_close_50_618`
- R249 artifact is valid and written
- R249 artifact remains unsigned
- R249 `submit_allowed=false`
- R249 `binance_call_allowed=false`
- R249 `network_allowed=false`
- R249 `order_placed=false`
- main order preview is `SELL MARKET quantity 0.007`
- stop order preview is `BUY STOP_MARKET reduceOnly=true stopPrice 62844.6`
- take-profit order preview is `BUY TAKE_PROFIT_MARKET reduceOnly=true stopPrice 60941.7`
- all request templates are preview-only and unsigned
- `/fapi/v1/order` appears only as a future signed endpoint template, not as a network call

## Primary Commands

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-signature-gate-preview
```

Rejected confirmation check:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-signature-gate-preview \
  --record-signature-gate-preview \
  --confirm-tiny-live-signature-gate-preview "wrong"
```

Record preview only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-signature-gate-preview \
  --record-signature-gate-preview \
  --confirm-tiny-live-signature-gate-preview "I CONFIRM TINY LIVE SIGNATURE GATE PREVIEW RECORDING ONLY; NO SIGNED REQUEST; NO ORDER; NO BINANCE CALL."
```

## Next Phase

R251 should consume the recorded R250 signature preview and create a local signed request artifact only under its own exact confirmation. R251 must define a safe secret access strategy and still forbid Binance/network calls, submit, and order placement.
