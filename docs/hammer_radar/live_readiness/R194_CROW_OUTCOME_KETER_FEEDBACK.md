# R194 Crow Outcome Keter Feedback

R194 feeds recorded R193 `three_black_crows` outcome mapping evidence into a paper-only Keter feedback projection. It is diagnostic/audit evidence only; it does not write scoring config, promote origins, promote lanes, or authorize live execution.

## Target

- signal origin: `three_black_crows`
- primary lane: `BTCUSDT|8m|short|ladder_close_50_618`
- reference origin: `hammer_wick_reversal`
- R193 input ledger: `logs/hammer_radar_forward/crow_outcome_mapping_preview.ndjson`
- R191 context ledger: `logs/hammer_radar_forward/keter_rescore_after_three_black_crows.ndjson`
- R194 ledger: `logs/hammer_radar_forward/crow_outcome_keter_feedback.ndjson`

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  crow-outcome-keter-feedback
```

Rejected recording:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  crow-outcome-keter-feedback \
  --record-feedback \
  --confirm-crow-outcome-keter-feedback "wrong"
```

Confirmed feedback record:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  crow-outcome-keter-feedback \
  --record-feedback \
  --confirm-crow-outcome-keter-feedback "I CONFIRM CROW OUTCOME KETER FEEDBACK RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

## Behavior

- Reads the latest recorded R193 crow outcome mapping for the target lane.
- Extracts best-window outcome quality:
  - mapped count
  - favorable close rate
  - simple success and failure rates
  - average close return
  - average downside MFE and upside MAE
  - sample confidence
  - risk warning
- Computes a paper-only outcome feedback score.
- Projects an updated Three Black Crows Keter score from prior R191 context.
- Compares projected crow score against `hammer_wick_reversal`.
- Recommends whether R195 should rerun the lane matrix after outcome feedback.

## Current Recorded Evidence

The current R193 evidence shows:

- mapped detections: `23`
- best window: `10`
- supports short bias: `true`
- paper tracking recommended: `true`
- live ready: `false`
- needs more samples: `true`

R194 keeps this as paper-only feedback and caps confidence while sample count remains low.

## Safety Boundary

R194 is scoring feedback/audit only:

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

R195 should rerun the lane matrix after crow outcome feedback, compare hammer vs crows after outcome behavior, and keep all config/live/Binance/order gates closed.
