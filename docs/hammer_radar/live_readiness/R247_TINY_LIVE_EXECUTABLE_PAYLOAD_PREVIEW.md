# R247 Tiny-Live Executable Payload Preview

R247 previews executable-payload readiness for the official lane:

`BTCUSDT|8m|short|ladder_close_50_618`

It consumes the latest R246 refreshed non-executable payload artifact plus R245/R244/R242/R238/R236/R228 evidence. It does not create an executable payload. It reports the conversion requirements that must be satisfied before a future guarded write gate.

## Safety State

- Preview is default.
- Optional confirmed mutation is limited to `logs/hammer_radar_forward/tiny_live_executable_payload_preview.ndjson`.
- No executable payload artifact writes.
- No signed requests.
- No Binance/network calls.
- No order or test-order placement.
- No config/env/lane-control/risk-contract writes.
- No kill-switch disable.
- Official tiny-live lane remains unchanged.

## Primary Commands

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-executable-payload-preview
```

Rejected confirmation check:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-executable-payload-preview \
  --record-executable-payload-preview \
  --confirm-tiny-live-executable-payload-preview "wrong"
```

Record preview only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-executable-payload-preview \
  --record-executable-payload-preview \
  --confirm-tiny-live-executable-payload-preview "I CONFIRM TINY LIVE EXECUTABLE PAYLOAD PREVIEW RECORDING ONLY; NO EXECUTABLE PAYLOAD; NO SIGNATURE; NO ORDER; NO BINANCE CALL."
```

## Current Expected Result

- R246 payload refresh artifact found and valid.
- Quantity remains `0.007`.
- Notional after rounding remains `435.4721`.
- Base payload remains `executable=false`, `signed=false`, `submit_allowed=false`, `order_placed=false`.
- Price precision requirements are reported from R242.
- Final stop price is missing unless a safe local source is later supplied.
- Final take-profit price is missing unless a safe local source is later supplied.
- Executable payload creation is blocked by stop/take-profit levels.

## Next Phase

Recommended next engineering move:

`R248 Tiny-Live Stop / Take-Profit Source Gate`

R248 should establish a guarded local source for final stop and take-profit levels before any executable payload write gate. It must not sign, call Binance, submit, or place an order.
