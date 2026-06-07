# R218 Betrayal V2 Source Row Append

## Superseded

This draft is superseded by `R218_STRATEGY_EVIDENCE_REGISTRY_SOURCE_IDENTITY_MANIFEST`.
The R218 phase is now a strategy evidence registry / source identity manifest only.
It does not append v2 source rows.

Move any future row-append or betrayal source-family wiring work behind
`R219_REGISTRY_WIRING_FOR_BETRAYAL_SOURCE_FAMILY.md`, after the R218 registry is
available and still with no config writes, no Binance/network calls, no order
payloads, no live authorization, and no betrayal promotion.

## Purpose

Append paper-only betrayal source emitter v2 rows only when R217 produced schema-complete ready rows.

## Inputs

- `logs/hammer_radar_forward/betrayal_aggregate_decomposition.ndjson`
- R217 preview output from `betrayal-aggregate-decomposition`
- R216 v2 source emitter contract
- R212 event identity rules

## Required Behavior

- Read the latest R217 decomposition record or preview.
- Append only rows where `schema_complete=true`.
- Preserve `paper_only=true`, `live_authorized=false`, and `promotion_allowed=false`.
- Preserve explicit `original_direction`, `inverse_direction`, `entry_mode`, `source_identity`, `source_signal_id`, and timestamp fields.
- Do not append partial, blocked, aggregate-only, lane-direction-only, or no-identity rows.
- Do not count appended source rows as validated outcome samples.

## Non-Negotiable Safety

- No config writes.
- No env writes or mutations.
- No source registry definition edits.
- No Binance calls.
- No network calls.
- No order payloads.
- No order placement.
- No transfers or withdrawals.
- No lane mode changes.
- No risk contract writes.
- No signal origin promotion.
- No lane promotion.
- No betrayal promotion.
- No live authorization.
- No tiny-live readiness inference.

## Expected Output

- Append-only v2 source row ledger.
- Gap report for skipped partial/blocked rows.
- Safety object proving no live/config/order/network behavior occurred.

## Validation

- Focused R218 tests for append gating.
- R217/R216/R215/R212 related tests.
- Smoke preview and confirmed append with exact future phrase.
- Confirm env/config/feed diffs remain empty except the append-only R218 ledger when explicitly recorded.
