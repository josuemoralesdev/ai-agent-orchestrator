# R223 Betrayal Source Identity Normalizer

## Purpose

Use registry-backed R218/R219 requirements to normalize `source_identity` and `entry_mode` for betrayal rows only where local evidence already supports the values.

## Scope

- Read the R218 strategy evidence registry.
- Read R219 and R221 betrayal registry wiring/consumer reports.
- Inspect local betrayal source, direction, event, outcome, and capture ledgers.
- Produce a paper-only normalization preview.
- Append only an R223 normalization audit ledger after an exact confirmation phrase.
- Do not synthesize unsupported source identity, entry mode, direction, or outcomes.

## Safety

- No historical ledger rewrite.
- No config writes.
- No env writes or mutation.
- No live execution.
- No Binance/network calls.
- No order, test-order, or protective endpoint calls.
- No order payloads or signed requests.
- No live authorization.
- No betrayal, signal-origin, or lane promotion.
- No lane `tiny_live` mode changes.
- No risk contract config writes.

## Expected Validation

- Preview writes no record.
- Wrong confirmation rejects.
- Correct confirmation appends only the R223 ledger.
- Unsupported rows remain blocked.
- All normalized rows remain `paper_only=true`, `live_authorized=false`, and `promotion_allowed=false`.
- Existing R218, R219, R221, R217, R216, and R215 tests remain passing.
