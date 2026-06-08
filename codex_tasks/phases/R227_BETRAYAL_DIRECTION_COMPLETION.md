# R227 Betrayal Direction Completion

## Purpose

Resolve remaining missing `original_direction`, `inverse_direction`, and `emitted_direction` fields for partial R226 renormalized rows only where local evidence supports completion.

## Inputs

- `logs/hammer_radar_forward/betrayal_renormalize_with_entry_mode.ndjson`
- `logs/hammer_radar_forward/betrayal_direction_split_resolver.ndjson`
- `logs/hammer_radar_forward/betrayal_source_emitter_refresh.ndjson`
- `logs/hammer_radar_forward/betrayal_aggregate_decomposition.ndjson`
- R218 strategy evidence registry
- R219 registry wiring for betrayal source family

## Required Safety

- No config writes.
- No env mutation.
- No Binance/network calls.
- No order/test-order/protective endpoint calls.
- No order payloads.
- No live execution.
- No lane mode changes.
- No risk contract config writes.
- No betrayal, signal-origin, or lane promotion.
- No destructive ledger rewrite.

## Expected Behavior

- Complete direction fields only from explicit local direction evidence.
- Require `emitted_direction == inverse_direction` for resolver-ready preview status.
- Keep rows `paper_only=true`, `live_authorized=false`, and `promotion_allowed=false`.
- Keep incomplete rows blocked with explicit missing-field reasons.
- Do not append normalized source rows.
