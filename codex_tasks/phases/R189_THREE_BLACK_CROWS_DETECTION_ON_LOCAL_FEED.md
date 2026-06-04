# R189 Three Black Crows Detection On Local Feed

## Purpose

Run the Three Black Crows detector against the R188 local candle feed adapter
and produce paper-only detection summaries or tags when true local OHLC
detections exist.

## Scope

- Consume `src/app/hammer_radar/operator/local_candle_feed_adapter.py`.
- Use `logs/hammer_radar_forward/candle_archive/BTCUSDT_8m.ndjson` or the
  explicitly confirmed normalized local feed as local input.
- Run strict and loose Three Black Crows detection for `BTCUSDT` `8m`.
- Produce paper-only detection output for
  `BTCUSDT|8m|short|ladder_close_50_618`.
- Do not synthesize OHLC from signal summaries.

## Non-Negotiables

- no live execution
- no config writes
- no env writes or env mutation
- no Binance calls
- no network calls
- no order or test-order calls
- no transfer or withdraw calls
- no signed requests
- no executable payloads
- no lane mode changes
- no tiny-live arming
- no lane promotion
- no signal-origin promotion
- no fake OHLC

## Expected Validation

- focused R189 detector/local-feed tests
- related R188 adapter tests
- related R185/R186 detector/feed integration tests
- smoke preview proving `paper_only=true`, `live_authorized=false`, and no
  config/env/feed writes by default
