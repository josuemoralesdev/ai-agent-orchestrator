# R186 Three Black Crows Feed Integration And Paper Tagging

## Purpose

Integrate R185 Three Black Crows detector output into local signal-origin feed tagging and paper-only records.

R186 should consume R185 detector preview records and make `three_black_crows` visible in paper signal-origin summaries when local detections exist.

## Scope

- Read local R185 detector records from `logs/hammer_radar_forward/three_black_crows_detector.ndjson`.
- Add paper-only signal-origin feed tagging for detected candidates.
- Keep `signal_origin=three_black_crows`.
- Preserve target lane context, especially `BTCUSDT|8m|short|ladder_close_50_618`.
- Update tests and docs for paper-only detector-output consumption.

## Non-Negotiable Safety

R186 must not:

- place orders
- call Binance
- call order, test-order, protective, transfer, or withdraw endpoints
- create order payloads
- create executable payloads
- create signed requests
- write env files
- write config files
- write lane config
- write risk-contract config
- change lane modes
- set any lane `tiny_live`
- promote `three_black_crows`
- promote any lane
- authorize live execution

## Expected Behavior

If R185 detections exist locally:

- tag paper/feed records with `signal_origin=three_black_crows`
- report paper-only lane/origin counts
- keep `paper_only=true`
- keep `live_authorized=false`

If no R185 detections exist:

- report no detector-backed records available
- recommend running R185 after candle-feed integration
- do not fake detections

## Validation

Run focused tests for:

- R185 detector record consumption
- R182/R183/R184 compatibility after feed tagging
- no env/config mutation
- no Binance calls
- no order/live/transfer/withdraw actions
- no lane or signal-origin promotion
