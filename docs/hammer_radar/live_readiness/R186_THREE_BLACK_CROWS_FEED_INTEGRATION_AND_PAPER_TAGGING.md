# R186 Three Black Crows Feed Integration and Paper Tagging

R186 wires the R185 Three Black Crows detector preview into local feed discovery and paper-only tag output for:

- primary lane: `BTCUSDT|8m|short|ladder_close_50_618`
- signal origin: `three_black_crows`
- detector mode: `strict` or `loose_preview`

## Scope

R186 reads local files under `logs/hammer_radar_forward/` only:

- `candles.ndjson`
- `ohlc.ndjson`
- `klines.ndjson`
- `*candles*.ndjson`
- `signals.ndjson`
- `multi_symbol_paper_scans.ndjson`
- `multi_lane_paper_harvester.ndjson`

Real OHLC candle files are the only valid detector input. Signal, scan, and harvester logs may produce synthetic candidate context, but that context is always marked:

```json
{"not_valid_for_three_black_crows_detection": true}
```

Synthetic signal context never becomes fake open/high/low/close data.

## Command

Strict preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  three-black-crows-feed-integration \
  --symbol BTCUSDT \
  --timeframe 8m \
  --mode strict \
  --latest-candles 500
```

Loose preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  three-black-crows-feed-integration \
  --symbol BTCUSDT \
  --timeframe 8m \
  --mode loose_preview \
  --latest-candles 500
```

Confirmed recording writes append-only records to:

```text
logs/hammer_radar_forward/three_black_crows_feed_integration.ndjson
logs/hammer_radar_forward/three_black_crows_paper_tags.ndjson
```

The required phrase is:

```text
I CONFIRM THREE BLACK CROWS FEED INTEGRATION RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL.
```

## Status Behavior

- `LOCAL_OHLC_FEED_MISSING`: no local OHLC files exist.
- `SYNTHETIC_SIGNAL_FEED_AVAILABLE`: local signal context exists, but it is not valid candle data.
- `INSUFFICIENT_CANDLE_DATA`: a local OHLC file exists, but fewer than three valid candles normalize for the target.
- `NO_DETECTIONS_FOUND`: local OHLC exists and detector ran, but no Three Black Crows sequence was found.
- `DETECTIONS_TAGGED`: detector found paper-only candidates and R186 produced paper tags.

## Safety Boundary

R186 is feed integration and paper tagging only:

- no Binance calls
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
- `paper_only=true`
- `live_authorized=false`

## Next Possible R187

R187 should determine how to create or consume a local OHLC candle feed without Binance calls. It should keep all output preview-only, avoid env/config writes, avoid live execution, and keep Three Black Crows unpromoted.
