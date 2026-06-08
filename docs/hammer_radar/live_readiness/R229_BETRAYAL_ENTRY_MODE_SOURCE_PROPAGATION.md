# R229 Betrayal Entry Mode Source Propagation

R229 adds a paper-only source propagation preview for betrayal rows after R227
proved direction is mostly present but `entry_mode` and `lane_key` remain the
main resolver-ready blockers.

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-entry-mode-source-propagation
```

Record the R229 audit ledger only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-entry-mode-source-propagation \
  --record-propagation \
  --confirm-betrayal-entry-mode-source-propagation "I CONFIRM BETRAYAL ENTRY MODE SOURCE PROPAGATION RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

## Behavior

- Uses R227 direction-completed rows as the primary base.
- Uses R226 renormalized previews as fallback base evidence.
- Joins R225 entry-mode evidence and R224A source-identity evidence by stable
  local source keys.
- Propagates `entry_mode` only from explicit local evidence, `lane_key`,
  structured `source_signal_id`/`source_capture_id`, or an explicit source
  contract carrying entry mode.
- Does not infer entry mode from common defaults, candidate label, timeframe,
  or aggregate context.
- Previews `lane_key` only when symbol, timeframe, emitted direction, and
  registry-valid entry mode are present.
- Marks `resolver_ready_preview=true` only when the R218/R219
  `betrayal_source_emitter_v2` registry contract is complete and
  `emitted_direction == inverse_direction`.

## Safety State

- Preview writes no records.
- Confirmed recording appends only
  `logs/hammer_radar_forward/betrayal_entry_mode_source_propagation.ndjson`.
- No normalized source rows are appended.
- No env/config/risk/lane/registry/scoring/matrix files are written.
- No Binance/network/order/test-order/protective/transfer/withdraw path is called.
- `paper_only=true`, `live_authorized=false`, and `promotion_allowed=false`.
- Betrayal, signal origins, and lanes are not promoted.
- Source propagation is not tiny-live readiness and not live authorization.

## Current Local Interpretation

R229 may produce resolver-ready previews when explicit local entry-mode evidence
can be joined to R227 direction-complete rows. It still does not append
normalized rows. R224 append must remain separately guarded and require the
latest R229 `resolver_ready_preview_rows > 0`.

## Next Safe Moves

- Keep BTCUSDT 8m short capture threshold checks separate.
- Use R230 to wire future betrayal emitter/capture surfaces so `entry_mode`
  and `lane_key` are emitted explicitly at creation time.
- Run R224 append only after R229 reports `resolver_ready_preview_rows > 0`
  and the guarded R224 phase validates all append preconditions.
