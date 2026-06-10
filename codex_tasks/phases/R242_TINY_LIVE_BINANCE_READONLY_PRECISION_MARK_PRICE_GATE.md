# R242 Tiny-Live Binance Readonly Precision Mark Price Gate

## Intent

Consume R241 Tiny-Live Precision and Mark Price Preview and create a separately guarded read-only Binance precision/mark-price gate.

## Required Boundary

- Requires an exact operator confirmation phrase before any read-only Binance call is allowed.
- Allows only read-only exchange info and mark-price endpoints if explicitly implemented.
- Must not call any order endpoint.
- Must not create executable payloads.
- Must not create signed trading requests.
- Must not place real or test orders.
- Must not mutate `.env`, configs, lane controls, scheduler/fisherman configs, strategy ledgers, paper outcome ledgers, or promotion ledgers.
- Must not disable the kill switch.
- Must keep official lane unchanged: `BTCUSDT|8m|short|ladder_close_50_618`.

## Inputs

- `logs/hammer_radar_forward/tiny_live_precision_and_mark_price_preview.ndjson`
- R240 non-executable order payload artifact
- R238 order preflight artifact
- R236 lane-arm artifact
- R230 risk contract config
- R228 tiny-live 10-of-10 evidence packet
- `configs/hammer_radar/tiny_live_risk_contracts.json` read-only
- `configs/hammer_radar/lane_controls.json` read-only

## Expected Output

R242 should report:

- whether the R241 preview is present and valid
- whether read-only exchange-info precision was fetched under the R242 gate
- whether read-only mark price was fetched under the R242 gate
- quantity preview using fetched read-only metadata and mark price
- remaining blockers before executable payload creation
- explicit non-actions
- recommended next operator and engineering moves

## Non-Actions

- No live connector submit.
- No order endpoint.
- No executable order payload.
- No signed order request.
- No signed trading request.
- No order placement.
- No config/env/lane-control mutation.
