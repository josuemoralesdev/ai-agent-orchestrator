# R192 Lane Matrix After Crow Rescoring

R192 refreshes the lane x signal-origin comparison after R191 rescored `three_black_crows` from detector evidence. It reads local R191, R184, and R181 surfaces, compares the primary BTCUSDT 8m short hammer pair against the rescored Three Black Crows pair, and records an append-only audit matrix only after exact confirmation.

## Target

- primary lane: `BTCUSDT|8m|short|ladder_close_50_618`
- reference origin: `hammer_wick_reversal`
- rescored origin: `three_black_crows`
- R191 rescore input: `logs/hammer_radar_forward/keter_rescore_after_three_black_crows.ndjson`
- R184 matrix input: `logs/hammer_radar_forward/signal_origin_lane_matrix.ndjson`
- R181 ranking input: `logs/hammer_radar_forward/multi_lane_evidence_rankings.ndjson`
- R192 ledger: `logs/hammer_radar_forward/lane_matrix_after_crow_rescoring.ndjson`

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  lane-matrix-after-crow-rescoring
```

Rejected recording:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  lane-matrix-after-crow-rescoring \
  --record-matrix \
  --confirm-lane-matrix-after-crow-rescore "wrong"
```

Confirmed matrix recording:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  lane-matrix-after-crow-rescoring \
  --record-matrix \
  --confirm-lane-matrix-after-crow-rescore "I CONFIRM LANE MATRIX AFTER CROW RESCORING RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

## Behavior

- Reuses R184 pair scoring for lane score, Keter score, tagged density, and fresh-capture threshold progress.
- Replaces the R184 `three_black_crows` registry-only score with the R191 rescored Keter value.
- Carries R189/R190 evidence counts into the crow pair comparison.
- Keeps `hammer_wick_reversal` as the current best pair when its pair score remains higher.
- Marks `three_black_crows` as a paper-tracking candidate that still needs paper outcome mapping.
- Recommends R193 crow outcome mapping preview before any promotion review.
- Emits a candle-pattern family reuse plan for `three_white_soldiers`, engulfing detectors, exhaustion wick, and retest families.

## Safety Boundary

R192 is matrix/audit only:

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

R193 should map Three Black Crows detections to future paper outcome windows and estimate post-detection behavior without live execution, config writes, Binance calls, or network calls.
