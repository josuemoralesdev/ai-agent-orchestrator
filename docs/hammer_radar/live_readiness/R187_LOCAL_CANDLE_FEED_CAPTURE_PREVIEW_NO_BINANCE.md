# R187 Local Candle Feed Capture Preview No Binance

R187 audits local candle-like files for the Three Black Crows detector without
calling Binance, writing config, writing a candle feed, or placing orders.

## Scope

Target context:

- symbol: `BTCUSDT`
- timeframe: `8m`
- primary lane: `BTCUSDT|8m|short|ladder_close_50_618`
- consumer: `three_black_crows_detector`

The preview scans local files under `logs/hammer_radar_forward/`:

- flat candle-like files such as `candles.ndjson`, `ohlc.ndjson`, and `klines.ndjson`
- wildcard local candle files matching `*candle*.ndjson`, `*ohlc*.ndjson`, and `*kline*.ndjson`
- archive files under `candle_archive/*.ndjson`
- signal context files: `signals.ndjson`, `multi_symbol_paper_scans.ndjson`, `multi_lane_paper_harvester.ndjson`

Signal, scan, and harvester records are context only. They are rejected as
synthetic/signal-only sources and are never promoted into OHLC.

## Valid Candle Shape

Required fields:

```text
symbol
timeframe
open_time
open
high
low
close
source
```

Optional fields:

```text
timestamp
close_time
volume
generated_at
```

Rules:

- `open`, `high`, `low`, and `close` must be numeric.
- `high >= max(open, close)`.
- `low <= min(open, close)`.
- `symbol` and `timeframe` must match the requested target.
- signal price summaries are not valid OHLC.
- synthetic OHLC flags or signal-only identities reject the record.

## Command

Preview only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  local-candle-feed-preview \
  --symbol BTCUSDT \
  --timeframe 8m \
  --latest-candles 500
```

Wrong confirmation is rejected and writes no record:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  local-candle-feed-preview \
  --record-preview \
  --confirm-local-candle-feed-preview "wrong"
```

Confirmed recording writes only the preview ledger:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  local-candle-feed-preview \
  --symbol BTCUSDT \
  --timeframe 8m \
  --latest-candles 500 \
  --record-preview \
  --confirm-local-candle-feed-preview "I CONFIRM LOCAL CANDLE FEED PREVIEW RECORDING ONLY; NO FEED WRITE; NO ORDER; NO BINANCE CALL."
```

Ledger:

```text
logs/hammer_radar_forward/local_candle_feed_capture_previews.ndjson
```

Candidate future feed path, preview only:

```text
logs/hammer_radar_forward/candles_BTCUSDT_8m.ndjson
```

## Local Discovery Result

The current repo has local archive candle files, including:

```text
logs/hammer_radar_forward/candle_archive/BTCUSDT_8m.ndjson
```

Those records contain true local OHLC fields and can make
`feed_readiness=VALID_LOCAL_OHLC_FEED_AVAILABLE` in the R187 preview. R187 still
does not write the candidate feed by default.

## Safety Boundary

R187 is preview/audit only:

- no Binance calls
- no network calls
- no orders or test orders
- no transfer or withdraw calls
- no order payloads
- no executable payloads
- no signed requests
- no env writes or env mutation
- no config writes
- no candle feed writes
- no lane config writes
- no risk-contract config writes
- no lane mode changes
- no tiny-live arming
- no lane promotion
- no signal-origin promotion
- no fake OHLC

## Next Possible R188

R188 should implement a local-only adapter that reads valid OHLC files supplied
by the operator and optionally writes a normalized candle feed only after exact
confirmation. It must remain no-network, no-Binance, no-config-write, and
non-executing.
