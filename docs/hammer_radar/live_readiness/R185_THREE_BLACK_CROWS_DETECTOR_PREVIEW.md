# R185 Three Black Crows Detector Preview

R185 follows R184 because `three_black_crows` is already registered and scored as a high-priority detector gap, but R184 correctly keeps it out of paper-ready lane/origin scoring while the detector is missing.

## Detector Definition

R185 defines a paper-only bearish Three Black Crows preview detector for:

- signal origin: `three_black_crows`
- detector version: `r185_preview`
- primary lane context: `BTCUSDT|8m|short|ladder_close_50_618`
- direction: `short`

The detector requires exactly three consecutive bearish candles:

- each candle has `close < open`
- closes step down: third close < second close < first close
- bodies are meaningful relative to candle range
- output remains `paper_only=true`
- output remains `live_authorized=false`

## Strict vs Loose Preview

`strict` mode requires:

- three consecutive bearish candles
- lower closes across the sequence
- each body ratio is at least `0.5`
- second and third opens are within or near the previous candle body

`loose_preview` mode requires:

- three consecutive bearish candles
- lower closes across the sequence
- each body ratio is at least `0.35`

Loose preview exists only to find possible local candidates for later paper tagging review. It is not a live-readiness or promotion signal.

## Missing OHLC Behavior

R185 does not call Binance or fetch market data. It reads only local candle/OHLC NDJSON files under `logs/hammer_radar_forward/`.

If no local OHLC feed exists, the detector reports:

- `status=THREE_BLACK_CROWS_DETECTOR_BLOCKED`
- `detector_status=MISSING_OHLC_FEED`
- blocker `missing_ohlc_feed`
- recommended engineering move to run R186 feed integration

It does not fake detections.

## Command

Strict preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  three-black-crows-detector \
  --symbol BTCUSDT \
  --timeframe 8m \
  --mode strict \
  --latest-candles 500
```

Loose preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  three-black-crows-detector \
  --symbol BTCUSDT \
  --timeframe 8m \
  --mode loose_preview \
  --latest-candles 500
```

Confirmed recording writes append-only detector preview records to:

```text
logs/hammer_radar_forward/three_black_crows_detector.ndjson
```

The required phrase is:

```text
I CONFIRM THREE BLACK CROWS DETECTOR RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL.
```

## Safety Boundary

R185 is detector preview only:

- no live execution
- no Binance calls
- no order, test-order, transfer, or withdraw calls
- no order payloads
- no executable payloads
- no signed requests
- no env writes
- no config writes
- no lane config writes
- no risk-contract config writes
- no lane mode changes
- no tiny-live arming
- no lane promotion
- no signal-origin promotion

## Next Possible R186

R186 should integrate detector output into local signal-origin feed tagging and paper records. It must remain paper-only, avoid config writes, avoid Binance calls, avoid order payloads, and keep `three_black_crows` unpromoted until later evidence review phases explicitly change that boundary.
