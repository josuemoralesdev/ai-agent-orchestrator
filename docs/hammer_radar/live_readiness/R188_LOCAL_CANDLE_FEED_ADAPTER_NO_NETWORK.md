# R188 Local Candle Feed Adapter No Network

R188 adds a local-only adapter for the R187 valid candle archive feed. It reads
true OHLC records from `candle_archive`, normalizes them for detector consumers,
and runs the Three Black Crows detector preview without Binance, network,
orders, config writes, or live authorization.

## Target

- symbol: `BTCUSDT`
- timeframe: `8m`
- primary lane: `BTCUSDT|8m|short|ladder_close_50_618`
- signal origin: `three_black_crows`
- source feed: `logs/hammer_radar_forward/candle_archive/BTCUSDT_8m.ndjson`
- optional normalized output: `logs/hammer_radar_forward/candles_BTCUSDT_8m.ndjson`

The normalized output is not written by default. It is written only when the
operator supplies the exact normalized-feed write confirmation phrase.

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  local-candle-feed-adapter \
  --symbol BTCUSDT \
  --timeframe 8m \
  --latest-candles 500
```

Rejected recording:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  local-candle-feed-adapter \
  --record-adapter \
  --confirm-local-candle-feed-adapter "wrong"
```

Confirmed adapter recording only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  local-candle-feed-adapter \
  --symbol BTCUSDT \
  --timeframe 8m \
  --latest-candles 500 \
  --record-adapter \
  --confirm-local-candle-feed-adapter "I CONFIRM LOCAL CANDLE FEED ADAPTER RECORDING ONLY; NO FEED WRITE; NO ORDER; NO BINANCE CALL."
```

Confirmed normalized local feed write only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  local-candle-feed-adapter \
  --symbol BTCUSDT \
  --timeframe 8m \
  --latest-candles 500 \
  --write-normalized-feed \
  --confirm-normalized-candle-feed-write "I CONFIRM NORMALIZED LOCAL CANDLE FEED WRITE ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

Ledger:

```text
logs/hammer_radar_forward/local_candle_feed_adapter.ndjson
```

## Valid Candle Shape

Required:

```text
symbol
timeframe
open_time or timestamp
open
high
low
close
source
```

Optional:

```text
close_time
volume
generated_at
```

Rules:

- `open`, `high`, `low`, and `close` must be numeric.
- `high >= max(open, close)`.
- `low <= min(open, close)`.
- `symbol` and `timeframe` must match the requested target.
- signal price-only summaries are not valid OHLC.
- synthetic signal contexts are not promoted into OHLC.

## Output

The adapter reports:

- source feed path, source availability, loaded records, valid records, and invalid records
- normalized record count, latest candle time, sample normalized candle, and output path
- detector readiness and blockers
- strict and loose Three Black Crows detector counts
- paper-only and live-unauthorized detector result
- next operator and engineering moves
- safety flags proving no live/config/network/order path was used

## Safety Boundary

R188 is local adapter and detector-readiness only:

- no Binance calls
- no network calls
- no orders or test orders
- no transfer or withdraw calls
- no order payloads
- no executable payloads
- no signed requests
- no env writes or env mutation
- no config writes
- no lane config writes
- no risk-contract config writes
- no lane mode changes
- no tiny-live arming
- no lane promotion
- no signal-origin promotion
- no fake OHLC

## Next Phase

R189 should run paper-only Three Black Crows detection/tagging using the R188
adapter feed. It must remain no-network, no-Binance, no-config-write, and
non-executing.
