# R188 Local Candle Feed Adapter No Network

## Purpose

Implement a local-only adapter for valid OHLC candle files discovered by R187.
The adapter should let the Three Black Crows detector consume true local candle
records without Binance calls or network access.

## Scope

- Read local OHLC files only.
- Normalize records that contain `symbol`, `timeframe`, `open_time` or
  `timestamp`, numeric `open/high/low/close`, and `source`.
- Optionally write `logs/hammer_radar_forward/candles_BTCUSDT_8m.ndjson` only
  with an exact explicit confirmation phrase.
- Keep signal-only summaries and synthetic contexts rejected.

## Non-Negotiables

- no Binance calls
- no network calls
- no live execution
- no orders or test orders
- no transfer or withdraw calls
- no env writes or env mutation
- no config writes
- no risk-contract config writes
- no lane config writes
- no lane mode changes
- no tiny-live arming
- no fake OHLC
- no signal-origin promotion
- no lane promotion

## Validation

- py_compile for the adapter and CLI wiring
- focused adapter tests
- related Three Black Crows detector/feed integration tests
- smoke preview proving `would_write_feed_now=false` unless confirmed
- safety output proving no order/network/config/env mutation
