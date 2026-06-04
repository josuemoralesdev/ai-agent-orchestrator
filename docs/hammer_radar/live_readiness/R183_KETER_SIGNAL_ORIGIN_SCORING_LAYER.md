# R183 Keter Signal Origin Scoring Layer

R183 follows R182 by scoring the paper-only signal origins that R182 registered and tagged.

Keter is a signal-quality layer. It ranks why a setup exists before any future lane x origin matrix. It is not live authority, does not change lane modes, and does not promote any origin.

## Why R183 Follows R182

R182 created the origin registry and feed summary. It separated origins with existing support, such as `hammer_wick_reversal`, from registry-only pattern families, such as `three_black_crows`.

R183 consumes that registry/feed summary and adds quality scoring:

- detector availability
- tagged paper data
- lane coverage
- freshness
- historical paper outcomes when origin-tagged outcomes exist
- reversal/rejection context
- conflict penalties

## Registry-Only Origins

Registry-only origins are not trade-ready. They can be ranked as detector priorities, but their Keter score is capped below the paper-tracking candidate band until detector work exists.

`three_black_crows` is intentionally treated this way. It can become a high-priority detector recommendation because it is an operator-prioritized bearish pattern, but R183 does not mark it detected, paper-ready, live-ready, or promoted.

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  keter-signal-origin-scoring
```

Rejected recording:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  keter-signal-origin-scoring \
  --record-scoring \
  --confirm-keter-origin-scoring "wrong"
```

Record scoring:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  keter-signal-origin-scoring \
  --record-scoring \
  --confirm-keter-origin-scoring "I CONFIRM KETER SIGNAL ORIGIN SCORING RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

## Output

The command reports:

- `keter_origin_rankings`
- `by_lane_origin_scores`
- `detector_priority_recommendations`
- `origin_tracking_recommendations`
- `current_best_origin`
- `recommended_next_operator_move`
- `recommended_next_engineering_move`
- `do_not_run_yet`
- `safety`

## Safety Boundary

R183 is scoring/audit only:

- no live execution
- no config writes
- no env writes
- no lane config writes
- no risk-contract config writes
- no lane mode changes
- no Binance calls
- no order, test-order, transfer, or withdraw calls
- no executable payloads
- no signed requests
- no signal-origin promotion

## Next Possible R184

R184 can combine R181 lane ranking with R183 signal-origin scores into a lane x origin matrix for paper tracking decisions only. It should preserve the same no-live, no-config-write boundary.
