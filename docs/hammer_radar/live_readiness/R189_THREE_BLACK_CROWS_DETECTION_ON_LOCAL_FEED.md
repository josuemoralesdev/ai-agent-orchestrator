# R189 Three Black Crows Detection On Local Feed

R189 runs paper-only Three Black Crows detection against the R188 local candle
feed adapter for `BTCUSDT` `8m`. It produces local detection records and
signal-origin paper tags for `three_black_crows` linked to
`BTCUSDT|8m|short|ladder_close_50_618`.

## Target

- symbol: `BTCUSDT`
- timeframe: `8m`
- primary lane: `BTCUSDT|8m|short|ladder_close_50_618`
- signal origin: `three_black_crows`
- local source: `logs/hammer_radar_forward/candle_archive/BTCUSDT_8m.ndjson`
- detection ledger: `logs/hammer_radar_forward/three_black_crows_local_detections.ndjson`
- paper tag ledger: `logs/hammer_radar_forward/three_black_crows_paper_tags.ndjson`

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  three-black-crows-local-detection \
  --symbol BTCUSDT \
  --timeframe 8m \
  --latest-candles 500 \
  --mode both
```

Rejected recording:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  three-black-crows-local-detection \
  --record-detection \
  --confirm-three-black-crows-local-detection "wrong"
```

Confirmed detection and paper-tag recording:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  three-black-crows-local-detection \
  --symbol BTCUSDT \
  --timeframe 8m \
  --latest-candles 500 \
  --mode both \
  --record-detection \
  --confirm-three-black-crows-local-detection "I CONFIRM THREE BLACK CROWS LOCAL DETECTION RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

## Behavior

- Reads true local OHLC records through the R188 local candle adapter.
- Runs strict and/or loose-preview Three Black Crows detector modes.
- Emits paper-only detection records in preview output.
- Appends detection and tag ledgers only after the exact R189 confirmation.
- Marks `three_black_crows` as locally detected for future review feedback only.
- Recommends R190 to sync evidence back into registry/Keter/matrix review
  surfaces without promotion.

## Safety Boundary

R189 is local detector/tagging only:

- no Binance calls
- no network calls
- no orders or test orders
- no transfer or withdraw calls
- no order payloads
- no executable payloads
- no signed requests
- no env writes or env mutation
- no config writes
- no candle-feed writes
- no lane config writes
- no risk-contract config writes
- no lane mode changes
- no tiny-live arming
- no lane promotion
- no signal-origin promotion
- no fake OHLC

## Next Phase

R190 should sync the R189 detector evidence back into the signal-origin
registry, Keter scoring, and lane matrix through review packets only. R190
must remain no-network, no-Binance, no-config-write, non-executing, and
paper-only.
