# R239 Tiny-Live Order Payload Preview

## Status

Implemented.

## Scope

R239 adds a preview-only, non-executable order payload shape for the official lane:

`BTCUSDT|8m|short|ladder_close_50_618`

The preview consumes:

- R238 tiny-live order preflight write gate
- R237 tiny-live order preflight preview
- R236 lane-arm write gate
- R234 live execution enable write gate
- R232 live authorization write gate
- R230 tiny-live risk contract config write gate and current `configs/hammer_radar/tiny_live_risk_contracts.json`
- R228 tiny-live 10/10 evidence packet
- read-only `configs/hammer_radar/lane_controls.json`

## Commands

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-order-payload-preview
```

Rejected recording attempt:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-order-payload-preview \
  --record-order-payload-preview \
  --confirm-tiny-live-order-payload-preview "wrong"
```

Record preview only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-order-payload-preview \
  --record-order-payload-preview \
  --confirm-tiny-live-order-payload-preview "I CONFIRM TINY LIVE ORDER PAYLOAD PREVIEW RECORDING ONLY; NO ORDER PAYLOAD; NO ORDER; NO BINANCE CALL."
```

## Ledger

Confirmed recording appends only:

`logs/hammer_radar_forward/tiny_live_order_payload_preview.ndjson`

## Safety Boundary

R239 does not:

- create an order payload artifact
- create an executable payload
- create signed order, trading, or read-only requests
- call Binance or any network endpoint
- place real or test orders
- mutate `.env`
- mutate `configs/hammer_radar/tiny_live_risk_contracts.json`
- mutate `configs/hammer_radar/lane_controls.json`
- disable the kill switch
- append paper outcomes, strategy performance, or strategy promotion status
- promote alternate or betrayal lanes

## Preview Result

When all R228-R238 artifacts are present and valid, R239 reports:

- `order_payload_preview_overall_status=TINY_LIVE_ORDER_PAYLOAD_PREVIEW_READY_FOR_FUTURE_GATE`
- `preview_only=true`
- `executable=false`
- `signed=false`
- `submit_allowed=false`
- `binance_call_allowed=false`
- `network_allowed=false`
- `quantity_preview=null`
- `quantity_source=requires_precision_and_mark_price_later`
- `order_payload_created=false`
- `executable_payload_created=false`
- `signed_order_request_created=false`
- `signed_trading_request_created=false`
- `order_placed=false`
- `live_ready_today=false`

The preview shape is deliberately incomplete before future gates. It still requires symbol precision checks, a mark/candidate price snapshot, quantity rounding, min-notional validation, final operator payload confirmation, a future payload write gate, a future signature step, and future Binance connectivity checks.

Future suggested confirmation phrase for a later write gate:

`I CONFIRM TINY LIVE ORDER PAYLOAD WRITE GATE ONLY; NON-EXECUTABLE PAYLOAD ARTIFACT ONLY; NO ORDER; NO BINANCE CALL.`

## Next Phase

Recommended next engineering phase:

R240 Tiny-Live Order Payload Write Gate.

R240 should consume the R239 preview and create a guarded non-executable order payload artifact write gate with an exact operator confirmation phrase, while still forbidding Binance/network calls, order placement, executable payload creation, signed requests, and kill-switch disable.
