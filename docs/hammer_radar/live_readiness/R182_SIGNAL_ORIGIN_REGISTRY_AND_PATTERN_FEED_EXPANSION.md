# R182 Signal Origin Registry and Pattern Feed Expansion

R182 follows R181 by adding the next paper-only evidence layer: signal origin.

R181 ranked lanes and kept `BTCUSDT|8m|short|ladder_close_50_618` as the current next-door candidate with medium confidence and insufficient fresh capture depth. Lane ranking answers where a trade may happen. R182 does not change that answer. It records why a setup may exist by creating a registry and feed summary over local paper ledgers only.

## Lane vs Signal Origin

Lane is the execution venue tuple:

- symbol
- timeframe
- direction
- entry mode

Signal origin is the reason family behind the setup:

- hammer or wick reversal
- golden-pocket rejection
- RSI divergence
- candle pattern family
- breakout or breakdown retest
- exhaustion wick

Entry feed remains the local paper-only recognition path. R182 only tags and summarizes existing paper records where current fields support inference. It does not trade any origin and does not promote any origin.

## Scope

R182 adds:

- `src/app/hammer_radar/operator/signal_origin_registry.py`
- `signal-origin-registry` in `src.app.hammer_radar.operator.inspect`
- `logs/hammer_radar_forward/signal_origin_registry.ndjson`

The registry reads:

- `logs/hammer_radar_forward/signals.ndjson`
- `logs/hammer_radar_forward/multi_symbol_paper_scans.ndjson`
- `logs/hammer_radar_forward/multi_lane_paper_harvester.ndjson`

## Registry Origins

Initial origins:

- `hammer_wick_reversal`
- `golden_pocket_rejection`
- `three_black_crows`
- `three_white_soldiers`
- `bearish_engulfing`
- `bullish_engulfing`
- `rsi_divergence_bearish`
- `rsi_divergence_bullish`
- `breakdown_retest`
- `breakout_retest`
- `exhaustion_wick`
- `unknown_or_unclassified`

Three Black Crows is registry-only in R182. The registry names the family, aliases, direction support, and safety boundary, but it does not claim detector availability unless a detector already exists.

Engulfing, retest, and exhaustion-wick families are also registry-only until later detector phases add explicit detection.

## Commands

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  signal-origin-registry \
  --latest-signals 1000 \
  --latest-harvest-records 500
```

Rejected recording:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  signal-origin-registry \
  --record-registry \
  --confirm-signal-origin-registry "wrong"
```

Record registry:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  signal-origin-registry \
  --latest-signals 1000 \
  --latest-harvest-records 500 \
  --record-registry \
  --confirm-signal-origin-registry "I CONFIRM SIGNAL ORIGIN REGISTRY RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

## Output

The command reports:

- `registry`
- `feed_summary.records_checked`
- `feed_summary.records_tagged`
- `feed_summary.by_origin`
- `feed_summary.by_lane_and_origin`
- `origin_gaps`
- `recommended_next_operator_move`
- `recommended_next_engineering_move`
- `do_not_run_yet`
- `safety`

## Keter Scoring Future Layer

R183 should add Keter signal-origin scoring over paper-only origins. The score can consider reversal strength, confirmation density, timeframe alignment, historical paper outcome, freshness, higher-timeframe conflict, and whether the origin is continuation or reversal. R183 must remain non-executing and must not write config.

## Safety Boundary

R182 safety remains:

- no live execution
- no config writes
- no env writes
- no lane mode changes
- no risk-contract config writes
- no Binance calls
- no order, test-order, transfer, or withdraw calls
- no executable payloads
- no signed requests
- no signal-origin promotion

The registry is paper-only metadata and audit output.
