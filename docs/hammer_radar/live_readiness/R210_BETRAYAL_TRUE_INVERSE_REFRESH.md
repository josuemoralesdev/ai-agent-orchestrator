# R210 Betrayal True Inverse Refresh

R210 is a paper-only local refresh for betrayal true-inverse validation evidence.
It exists to keep the R80/R81/R95-R100 betrayal thread visible after R209 and to
test whether local shadow/candle/capture evidence can become strict
true-inverse paper validation.

## Scope

- Primary candidate: `222m aggregate`
- Watchlist candidate: `88m aggregate`
- Optional historical watchlist: `55m aggregate` when present in docs/ledgers
- Output ledger: `logs/hammer_radar_forward/betrayal_true_inverse_refresh.ndjson`
- Local inputs only: R209 recheck, betrayal docs, betrayal shadow outcomes,
  shadow resolutions, true-paper outcomes, paper signals, candle archive, and
  full-spectrum captures

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-true-inverse-refresh
```

Record:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-true-inverse-refresh \
  --record-refresh \
  --confirm-betrayal-true-inverse-refresh "I CONFIRM BETRAYAL TRUE INVERSE REFRESH RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

Rejected confirmation:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-true-inverse-refresh \
  --record-refresh \
  --confirm-betrayal-true-inverse-refresh "wrong"
```

## Validation Model

R210 separates:

- naive inverse audit evidence
- shadow paper outcomes
- persisted shadow resolutions
- true-paper outcomes
- strict local candle-window preview resolution
- full-spectrum capture linkage
- Markov/Miro Fish prerequisites
- live readiness, which remains false

A sample can be counted only when symbol, timeframe, timestamp, direction,
entry/stop/take-profit schema, local candle coverage, strict temporal alignment,
and duplicate checks all pass. A raw full-spectrum 222m capture can seed future
tracking but is not counted as a validated true-inverse sample.

## Safety State

R210 does not call Binance or the network. It does not create order payloads,
write env/config/risk/lane/scoring/matrix state, promote signal origins or
lanes, disable the kill switch, set any lane to `tiny_live`, or authorize live
execution.

Expected safety result:

- `env_written=false`
- `config_written=false`
- `ledger_rewritten=false`
- `destructive_write=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `order_payload_created=false`
- `executable_payload_created=false`
- `network_allowed=false`
- `secrets_shown=false`
- `paper_live_separation_intact=true`
- `betrayal_live_authorized=false`
- `betrayal_promoted=false`

## Recommendations

- If refreshed local evidence exists, R211 may add betrayal-aware paper matrix
  context only.
- If true inverse evidence remains pending, R212 should build a deterministic
  betrayal event tracker for future schema-complete samples.
- Do not promote betrayal.
- Do not live-authorize betrayal.
