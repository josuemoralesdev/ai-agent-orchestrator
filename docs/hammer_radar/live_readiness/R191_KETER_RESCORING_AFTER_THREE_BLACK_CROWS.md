# R191 Keter Rescoring After Three Black Crows

R191 rescored `three_black_crows` after R189 local detector/tag evidence and R190 feedback sync. It is a review-only Keter surface: it reads local ledgers, compares the rescored origin against `hammer_wick_reversal`, and recommends a later lane-matrix rerun without editing registry, scoring, matrix, lane, risk, or env config.

## Target

- signal origin: `three_black_crows`
- primary lane: `BTCUSDT|8m|short|ladder_close_50_618`
- reference origin: `hammer_wick_reversal`
- feedback input: `logs/hammer_radar_forward/signal_origin_feedback_sync.ndjson`
- detector input: `logs/hammer_radar_forward/three_black_crows_local_detections.ndjson`
- paper-tag input: `logs/hammer_radar_forward/three_black_crows_paper_tags.ndjson`
- rescore ledger: `logs/hammer_radar_forward/keter_rescore_after_three_black_crows.ndjson`

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  keter-rescore-after-three-black-crows
```

Rejected recording:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  keter-rescore-after-three-black-crows \
  --record-rescore \
  --confirm-keter-rescore-after-crows "wrong"
```

Confirmed rescore recording:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  keter-rescore-after-three-black-crows \
  --record-rescore \
  --confirm-keter-rescore-after-crows "I CONFIRM KETER RESCORING AFTER THREE BLACK CROWS RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

## Behavior

- Reads the latest R190 feedback sync for `three_black_crows`.
- Reads R189 local detector records and paper tags as supporting evidence.
- Reads existing R183 Keter scoring when present, otherwise uses the R183 preview path.
- Improves detector availability scoring only because local detector evidence exists.
- Keeps historical outcome score at `0` until paper outcomes are mapped.
- Keeps lane coverage limited to the BTCUSDT 8m short evidence lane.
- Keeps `paper_only=true`, `live_authorized=false`, `signal_origin_promoted=false`, and `lane_promoted=false`.
- Recommends `RUN_R192_LANE_MATRIX_AFTER_CROW_RESCORING` when R190 feedback is ready.

## Safety Boundary

R191 is rescoring/audit only:

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

R192 should rerun the lane x signal-origin matrix after the R191 rescore and compare `BTCUSDT|8m|short|ladder_close_50_618 + hammer_wick_reversal` against `BTCUSDT|8m|short|ladder_close_50_618 + three_black_crows`. It must remain no-config-write, no-Binance, no-network, and non-executing.
