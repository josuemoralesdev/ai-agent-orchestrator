# R224 Betrayal Normalized Source Row Append

## Purpose

Append normalized `betrayal_source_emitter_v2` rows only when R223 reports `resolver_ready_rows > 0`, R226 reports `resolver_ready_preview_rows > 0`, R227 reports `resolver_ready_preview_rows > 0`, and R229 reports `resolver_ready_preview_rows > 0`.

## Inputs

- `logs/hammer_radar_forward/betrayal_source_identity_normalizer.ndjson`
- `logs/hammer_radar_forward/betrayal_renormalize_with_entry_mode.ndjson`
- `logs/hammer_radar_forward/betrayal_direction_completion.ndjson`
- `logs/hammer_radar_forward/betrayal_entry_mode_source_propagation.ndjson`
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
- Require the latest R226 renormalization preview to report `resolver_ready_preview_rows > 0`.
- Require the latest R227 direction completion preview to report `resolver_ready_preview_rows > 0`.
- Require the latest R229 entry-mode source propagation preview to report `resolver_ready_preview_rows > 0`.
- Preserve `paper_only=true`, `live_authorized=false`, and `promotion_allowed=false`.
- Report unchanged live/order safety fields.

## Blocked Conditions

- R223 ledger missing.
- R223 latest record has zero resolver-ready rows.
- R226 ledger missing.
- R226 latest record has `resolver_ready_preview_rows=0`.
- R227 ledger missing.
- R227 latest record has `resolver_ready_preview_rows=0`.
- R229 ledger missing.
- R229 latest record has `resolver_ready_preview_rows=0`.
- R224A collector missing.
- R224A latest record has `resolver_ready_preview_rows=0`.
- Any candidate is not registry-backed.
- Any row fails `betrayal_source_emitter_v2` validation.
- Any row implies live authorization, promotion, config writes, or execution.

R224 must explicitly refuse to append normalized rows when R224A evidence collection, R226 renormalization, R227 direction completion, or R229 entry-mode source propagation reports zero resolver-ready preview rows, even if contextual evidence exists. Partial evidence is not append authority.
