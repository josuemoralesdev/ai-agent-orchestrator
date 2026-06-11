# R245 Tiny-Live Order Payload Refresh Preview

R245 refreshes the preview-only tiny-live order payload shape for the official lane:

`BTCUSDT|8m|short|ladder_close_50_618`

It consumes the R244 adjusted risk contract, latest recorded R242 read-only precision/mark-price result, R240 non-executable payload artifact, R238 order preflight, R236 lane arm, and R228 evidence packet. It does not write a payload artifact and does not create an executable payload.

## Safety State

- Preview/recording only.
- Confirmed mutation is limited to `logs/hammer_radar_forward/tiny_live_order_payload_refresh_preview.ndjson`.
- No config writes.
- No env writes.
- No lane-control writes.
- No Binance/network calls.
- No signed requests.
- No executable payloads.
- No order placement.

## Primary Commands

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-order-payload-refresh-preview
```

Record:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-order-payload-refresh-preview \
  --record-payload-refresh-preview \
  --confirm-tiny-live-order-payload-refresh-preview "I CONFIRM TINY LIVE ORDER PAYLOAD REFRESH PREVIEW RECORDING ONLY; NO PAYLOAD WRITE; NO ORDER; NO BINANCE CALL."
```

Rejected confirmation check:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-order-payload-refresh-preview \
  --record-payload-refresh-preview \
  --confirm-tiny-live-order-payload-refresh-preview "wrong"
```

## Expected Preview

- `margin_budget_usdt=44`
- `leverage=10`
- `notional_cap_usdt=440`
- `quantity_preview=0.007` with the recorded R242 sample mark price around `62210.3` and step size `0.001`
- `notional_after_rounding=435.4721` for the R242 sample
- Stop and take-profit payload previews remain `preview_only=true`, `executable=false`, `signed=false`, and price fields remain `null`

## Next Phase

Recommended next engineering move:

`R246 Tiny-Live Order Payload Refresh Write Gate`

R246 should consume the recorded R245 refresh preview and write only a refreshed non-executable payload artifact after an exact operator confirmation. It must not create an executable payload, signed request, Binance call, or order.
