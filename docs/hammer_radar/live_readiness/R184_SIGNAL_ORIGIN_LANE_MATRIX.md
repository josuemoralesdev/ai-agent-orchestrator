# R184 Signal-Origin Lane Matrix

R184 follows R183 by composing lane ranking with signal-origin quality scoring.

R181 answered where paper evidence is strongest. R183 answered why a signal origin is worth tracking. R184 combines those surfaces into a paper-only lane x origin matrix so operator attention can stay on the strongest current pair while detector gaps are made explicit.

## Matrix Semantics

Lane means where the trade may happen, such as `BTCUSDT|8m|short|ladder_close_50_618`.

Signal origin means why the trade may exist, such as `hammer_wick_reversal` or `three_black_crows`.

The matrix scores each lane/origin pair using:

- R181 lane score
- lane fresh capture count and threshold progress
- R183 Keter origin score
- tagged lane/origin record count
- detector availability
- registry-only, unknown-origin, and reference-only penalties

The matrix does not promote lanes, promote origins, set lane mode, write config, write risk contracts, or authorize live execution.

## Current Best Pair

The expected current lead remains:

- lane: `BTCUSDT|8m|short|ladder_close_50_618`
- signal origin: `hammer_wick_reversal`

That pair can be marked ready for paper tracking when the R181 lane score, R183 Keter score, fresh capture evidence, detector support, and tagged lane/origin records lead the matrix. Fresh captures below threshold remain a blocker for any later tiny-live readiness path.

## Three Black Crows

`three_black_crows` is intentionally detector-priority, not trade-ready.

R182 registered it as a bearish origin family, and R183 treats it as high detector priority. R184 preserves that boundary by showing `BTCUSDT|8m|short|ladder_close_50_618` + `three_black_crows` in detector priority pairs while keeping pair readiness at `PAIR_NEEDS_DETECTOR`.

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  signal-origin-lane-matrix
```

Rejected recording:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  signal-origin-lane-matrix \
  --record-matrix \
  --confirm-signal-origin-lane-matrix "wrong"
```

Record matrix:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  signal-origin-lane-matrix \
  --record-matrix \
  --confirm-signal-origin-lane-matrix "I CONFIRM SIGNAL ORIGIN LANE MATRIX RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

Confirmed recording writes append-only local audit records to:

```text
logs/hammer_radar_forward/signal_origin_lane_matrix.ndjson
```

## Safety Boundary

R184 is matrix/scoring/audit only:

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

## Next Possible R185

R185 should build a Three Black Crows detector preview for the current lead lane. It should remain paper-only, avoid config writes, avoid Binance calls, avoid order payloads, and produce detector evidence before any origin can become paper-ready.
