# R224 Betrayal Normalized Source Row Append

## Purpose

Append normalized `betrayal_source_emitter_v2` rows only when R223 reports `resolver_ready_rows > 0`.

## Inputs

- `logs/hammer_radar_forward/betrayal_source_identity_normalizer.ndjson`
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

- Preview append candidates by default.
- Require an exact recording confirmation phrase for append-only writes.
- Append only rows that R223 marked `resolver_ready=true`.
- Preserve `paper_only=true`, `live_authorized=false`, and `promotion_allowed=false`.
- Report unchanged live/order safety fields.

## Blocked Conditions

- R223 ledger missing.
- R223 latest record has zero resolver-ready rows.
- Any candidate is not registry-backed.
- Any row fails `betrayal_source_emitter_v2` validation.
- Any row implies live authorization, promotion, config writes, or execution.
