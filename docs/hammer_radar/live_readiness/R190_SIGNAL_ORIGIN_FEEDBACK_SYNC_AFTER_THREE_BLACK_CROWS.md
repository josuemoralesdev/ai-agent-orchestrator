# R190 Signal Origin Feedback Sync After Three Black Crows

R190 syncs the R189 local Three Black Crows detector evidence into a review-only feedback packet for the signal-origin stack.

The phase reads R189 local detection and paper-tag ledgers, summarizes `three_black_crows` evidence for `BTCUSDT|8m|short|ladder_close_50_618`, and recommends future review movement from `REGISTRY_ONLY` to `DETECTOR_AVAILABLE_AFTER_REVIEW`. It does not edit registry definitions, Keter scoring records, lane matrix records, config, env, lane modes, or live execution state.

## Target

- signal origin: `three_black_crows`
- primary lane: `BTCUSDT|8m|short|ladder_close_50_618`
- local detection ledger: `logs/hammer_radar_forward/three_black_crows_local_detections.ndjson`
- paper tag ledger: `logs/hammer_radar_forward/three_black_crows_paper_tags.ndjson`
- feedback ledger: `logs/hammer_radar_forward/signal_origin_feedback_sync.ndjson`

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  signal-origin-feedback-sync \
  --signal-origin three_black_crows \
  --lane-key "BTCUSDT|8m|short|ladder_close_50_618"
```

Rejected recording:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  signal-origin-feedback-sync \
  --record-feedback \
  --confirm-signal-origin-feedback-sync "wrong"
```

Confirmed feedback recording:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  signal-origin-feedback-sync \
  --signal-origin three_black_crows \
  --lane-key "BTCUSDT|8m|short|ladder_close_50_618" \
  --record-feedback \
  --confirm-signal-origin-feedback-sync "I CONFIRM SIGNAL ORIGIN FEEDBACK SYNC RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

## Behavior

- Reads R189 local detector records.
- Reads R189 paper tags.
- Counts strict detections, loose-preview detections, and paper tags.
- Reports latest detection and tag timestamps.
- Recommends `DETECTOR_AVAILABLE_AFTER_REVIEW` for future registry review only.
- Recommends R191 Keter rescoring and a later lane-matrix rerun when detection evidence and tags both exist.
- Appends only `signal_origin_feedback_sync.ndjson` after exact confirmation.

## Safety Boundary

R190 is feedback/audit only:

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

R191 should rescore Keter after Three Black Crows detector evidence. It must remain paper-only, no-config-write, no-Binance, no-network, and non-executing.
