# R242 Tiny-Live Binance Read-Only Precision / Mark-Price Gate

## Status

Implemented as a separately guarded Binance Futures public read-only data gate for the official tiny-live lane:

`BTCUSDT|8m|short|ladder_close_50_618`

## Purpose

R242 consumes R241 precision/mark-price preview, R240 non-executable order payload artifact, R238 order preflight, R236 lane-arm artifact, R230 risk contract config, the current tiny-live risk contract config, and the R228 evidence packet.

Preview mode is default and performs no network call. A Binance public data fetch is allowed only after the exact R242 confirmation phrase.

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-binance-readonly-precision-mark-price-gate
```

Rejected fetch:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-binance-readonly-precision-mark-price-gate \
  --fetch-binance-readonly \
  --confirm-tiny-live-binance-readonly-fetch "wrong"
```

Confirmed read-only fetch:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-binance-readonly-precision-mark-price-gate \
  --fetch-binance-readonly \
  --confirm-tiny-live-binance-readonly-fetch "I CONFIRM BINANCE READONLY PRECISION MARK PRICE CHECK ONLY; NO ORDER; NO SIGNATURE; NO PRIVATE ENDPOINT."
```

## Allowed Mutation

Only this append-only ledger may be written after exact confirmation and successful read-only fetch:

`logs/hammer_radar_forward/tiny_live_binance_readonly_precision_mark_price_gate.ndjson`

## Allowed Public Endpoints

R242 allows only Binance Futures public GET endpoints:

- `GET /fapi/v1/exchangeInfo`
- `GET /fapi/v1/premiumIndex?symbol=BTCUSDT`

## Safety Boundary

R242 must not:

- call Binance order, test-order, batch-order, leverage, account, position, margin, transfer, or withdraw endpoints
- use API keys or API secrets
- create signed requests
- create executable or submit-ready payloads
- place real or test orders
- mutate `.env`
- mutate configs, risk contracts, lane controls, scheduler, or Fisherman config
- disable kill switch
- append paper outcomes, strategy performance, strategy promotion, or alternate lane promotion ledgers

The packet keeps:

- `binance_readonly_gate_only=true`
- `public_endpoints_only=true`
- `order_endpoint_allowed=false`
- `private_endpoint_allowed=false`
- `signed_request_allowed=false`
- `order_payload_created=false`
- `executable_payload_created=false`
- `signed_order_request_created=false`
- `signed_trading_request_created=false`
- `submit_allowed=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`

## Quantity Preview

When fetched precision and mark price are valid, R242 computes preview-only quantity:

- `quantity_raw = 44 / mark_price`
- `quantity_rounded = floor_to_step(quantity_raw, step_size)`
- `notional_after_rounding = quantity_rounded * mark_price`
- `min_notional_ok = notional_after_rounding >= min_notional`

This quantity preview is not an executable order payload.

## Next Phase

R243 should consume the R242 read-only precision/mark-price result and preview executable payload requirements or quantity application. R243 must still avoid signing, Binance order endpoints, private endpoints, submit, and order placement.
