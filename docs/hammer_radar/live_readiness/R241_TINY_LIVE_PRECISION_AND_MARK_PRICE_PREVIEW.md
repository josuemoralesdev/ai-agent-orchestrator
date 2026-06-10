# R241 Tiny-Live Precision And Mark Price Preview

## Status

Implemented as a preview-only precision, candidate price, and quantity-readiness packet for the official tiny-live lane:

`BTCUSDT|8m|short|ladder_close_50_618`

## Purpose

R241 consumes the R240 non-executable order payload artifact, R238 order preflight, R236 lane-arm artifact, R230 risk contract config, and R228 10-of-10 ready packet. It reports whether local precision metadata and a local mark/candidate price proxy already exist, then computes a quantity preview only when both are available from local read-only sources.

This phase is not Binance connectivity, executable payload creation, signing, or order placement.

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-precision-and-mark-price-preview
```

Rejected recording:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-precision-and-mark-price-preview \
  --record-precision-mark-price-preview \
  --confirm-tiny-live-precision-mark-price-preview "wrong"
```

Confirmed preview record:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-precision-and-mark-price-preview \
  --record-precision-mark-price-preview \
  --confirm-tiny-live-precision-mark-price-preview "I CONFIRM TINY LIVE PRECISION AND MARK PRICE PREVIEW RECORDING ONLY; NO BINANCE CALL; NO ORDER PAYLOAD; NO ORDER."
```

## Allowed Mutation

Only this append-only ledger may be written after exact confirmation:

`logs/hammer_radar_forward/tiny_live_precision_and_mark_price_preview.ndjson`

## Safety Boundary

R241 must not:

- call Binance or any network endpoint
- fetch live mark price
- create executable payloads
- create signed order, trading, or read-only requests
- place real or test orders
- mutate `.env`
- mutate configs or lane controls
- disable kill switch
- append paper outcomes, strategy performance, strategy promotion, or alternate lane promotion ledgers

The packet keeps:

- `precision_mark_price_preview_only=true`
- `order_payload_created=false`
- `executable_payload_created=false`
- `signed_order_request_created=false`
- `signed_trading_request_created=false`
- `order_placed=false`
- `network_allowed=false`

## Local Discovery

Local precision metadata is accepted only from existing local JSON/NDJSON sources with BTCUSDT symbol metadata including step size, tick size, and min-notional equivalent.

Local price is accepted only from existing local logs with BTCUSDT, a parseable timestamp, and a candidate/mark/last/close price. Missing precision or price keeps quantity preview blocked and recommends a later read-only Binance gate.

## Next Phase

R242 should consume the R241 preview and implement a separately guarded Binance read-only precision/mark-price gate. It may only allow explicitly confirmed read-only exchange-info and mark-price checks. It must not call order endpoints, create executable payloads, sign trading requests, or place orders.
