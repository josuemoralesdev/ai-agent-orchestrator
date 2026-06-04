# R193 Crow Outcome Mapping Preview

R193 maps R189 `three_black_crows` detections to local post-detection BTCUSDT 8m candle windows. It is a paper-only audit preview for short-bias follow-through; it is not trade PnL, readiness, promotion, or execution authority.

## Target

- primary lane: `BTCUSDT|8m|short|ladder_close_50_618`
- signal origin: `three_black_crows`
- detection input: `logs/hammer_radar_forward/three_black_crows_local_detections.ndjson`
- paper tag input: `logs/hammer_radar_forward/three_black_crows_paper_tags.ndjson`
- candle input: `logs/hammer_radar_forward/candle_archive/BTCUSDT_8m.ndjson`
- R193 ledger: `logs/hammer_radar_forward/crow_outcome_mapping_preview.ndjson`

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  crow-outcome-mapping-preview \
  --symbol BTCUSDT \
  --timeframe 8m \
  --lane-key "BTCUSDT|8m|short|ladder_close_50_618"
```

Rejected recording:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  crow-outcome-mapping-preview \
  --record-mapping \
  --confirm-crow-outcome-mapping "wrong"
```

Confirmed mapping record:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  crow-outcome-mapping-preview \
  --symbol BTCUSDT \
  --timeframe 8m \
  --lane-key "BTCUSDT|8m|short|ladder_close_50_618" \
  --record-mapping \
  --confirm-crow-outcome-mapping "I CONFIRM CROW OUTCOME MAPPING PREVIEW RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

## Behavior

- Reads the latest matching R189 local detection batch for `three_black_crows`.
- Matches R189 paper tags by detection id.
- Reads only the local R188/R187 BTCUSDT 8m candle archive.
- Maps each detection to 1, 3, 5, and 10 post-detection candles when future candles exist.
- Uses the detection candle close as the entry reference, or the next candle open only if the detection close is unavailable.
- Computes short-context preview metrics:
  - MFE downside percent
  - MAE upside percent
  - close-after-window return percent
  - favorable/adverse close flags
  - simple success/failure flags from preview thresholds
- Aggregates window rates and averages for paper-only interpretation.
- Recommends R194 only when mapped outcomes support short-bias feedback.

## Safety Boundary

R193 is outcome mapping/audit only:

- no Binance calls
- no network calls
- no orders or test orders
- no transfers or withdrawals
- no order payloads
- no executable payloads
- no signed requests
- no env writes or env mutation
- no config writes
- no registry config writes
- no scoring config writes
- no matrix config writes
- no lane config writes
- no risk-contract config writes
- no lane mode changes
- no tiny-live arming
- no signal-origin promotion
- no lane promotion
- no live authorization

## Next Phase

R194 should feed R193 outcome mapping into Keter/crow scoring as a paper-only diagnostic, without config writes, live execution, Binance calls, network calls, or promotion.
