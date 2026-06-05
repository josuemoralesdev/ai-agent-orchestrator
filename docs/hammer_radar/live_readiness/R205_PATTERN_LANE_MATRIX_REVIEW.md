# R205 Pattern Lane Matrix Review

R205 builds a paper-only lane x signal-origin matrix for the detector-backed pattern family. It composes R204 pattern Keter rescoring, R198 full-spectrum paper lane scope, and R192/R195 lane matrix reference evidence.

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  pattern-lane-matrix-review
```

Record matrix only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  pattern-lane-matrix-review \
  --record-matrix \
  --confirm-pattern-lane-matrix "I CONFIRM PATTERN LANE MATRIX REVIEW RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

Rejected confirmation:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  pattern-lane-matrix-review \
  --record-matrix \
  --confirm-pattern-lane-matrix "wrong"
```

## Scope

Origins considered:

- `hammer_wick_reversal`
- `three_black_crows`
- `bearish_engulfing`
- `exhaustion_wick`
- `bullish_engulfing`
- `three_white_soldiers`

Blocked origins:

- `breakdown_retest`
- `breakout_retest`

The matrix includes configured paper lanes plus R198 discovered unconfigured paper lanes. Discovered lanes are review candidates only and carry a caution penalty; R205 never writes lane config or changes lane mode.

## Safety State

R205 is matrix/audit only. It does not call Binance/network, create executable or signed payloads, place orders, transfer, withdraw, mutate env/config/risk/lane/registry/scoring/matrix state, promote signal origins, promote lanes, infer live readiness, or authorize pattern-family live trading.

Optional confirmed records append to:

```text
logs/hammer_radar_forward/pattern_lane_matrix_review.ndjson
```

## Next Work

- Keep full-spectrum paper harvesting running for fresh flow.
- Run R203 anchor x signal-origin confluence matrix when anchor review is needed.
- Use R206 to recheck tiny-live readiness gaps without config writes or live execution.
