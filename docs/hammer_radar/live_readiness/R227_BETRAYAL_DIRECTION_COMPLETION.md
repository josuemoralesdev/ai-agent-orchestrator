# R227 Betrayal Direction Completion

R227 adds a paper-only direction completion preview for betrayal source rows.
It reads R226 renormalized previews, R225 entry-mode evidence, R224A source
identity evidence, R215 direction split rows, the R218 registry, and local
shadow/true-paper/paper signal ledgers.

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-direction-completion
```

Record the R227 audit ledger only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-direction-completion \
  --record-completion \
  --confirm-betrayal-direction-completion "I CONFIRM BETRAYAL DIRECTION COMPLETION RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

## Safety State

- Preview writes no records.
- Confirmed recording appends only
  `logs/hammer_radar_forward/betrayal_direction_completion.ndjson`.
- No normalized source rows are appended.
- No env/config/risk/lane/registry/scoring/matrix files are written.
- No Binance/network/order/test-order/protective/transfer/withdraw path is called.
- `paper_only=true`, `live_authorized=false`, and `promotion_allowed=false`.
- Betrayal, signal origins, and lanes are not promoted.
- Direction completion is not tiny-live readiness and not live authorization.

## Direction Rules

R227 completes `original_direction`, `inverse_direction`, and
`emitted_direction` only from local explicit evidence:

- Existing source-row direction fields.
- R215 direction split rows.
- Local shadow outcome / true-paper / paper signal direction fields.
- Direction embedded in a structured source signal id.
- Opposite-of-original inverse direction only for betrayal/inverse-family rows
  after `original_direction` exists.
- `emitted_direction` is set only when `inverse_direction` exists and equals it.

R227 does not infer direction from aggregate candidate labels and does not use
aggregate context as directional proof.

## Resolver-Ready Preview

A row is resolver-ready only when the R218/R219
`betrayal_source_emitter_v2` registry contract is complete, including
candidate, timeframe, entry mode, direction fields, source identity, source
signal id, emitted signal id preview, source timestamp, lane key preview,
betrayal event identity/hash, outcome windows, and paper-only safety flags.

## Result From Current Local Ledgers

Use the command above for the current count. R227 may expose resolver-ready
previews if local direction evidence completes all registry-required fields,
but it still does not append normalized rows or change live readiness.

## Next Safe Moves

- Keep checking BTCUSDT 8m short capture threshold separately.
- Run R224 append only after R227 reports `resolver_ready_preview_rows > 0`
  and the guarded R224 append phase validates the latest evidence.
- Continue to keep funding and risk-contract readiness blocked until the
  tiny-live path independently satisfies its gates.
