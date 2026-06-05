# R205 Pattern Lane Matrix Review

## Purpose

Build a paper-only pattern-origin lane matrix review from R204 pattern Keter scores.

## Inputs

- R204 `pattern_keter_rescoring_family.ndjson`
- R202 `pattern_outcome_mapping_family.ndjson`
- R200 `pattern_family_feedback_sync.ndjson`
- Reference context for `hammer_wick_reversal` and `three_black_crows` when local ledgers contain it

## Scope

Include:

- `bearish_engulfing`
- `exhaustion_wick`
- `three_white_soldiers`
- `bullish_engulfing`

Keep blocked:

- `breakdown_retest`
- `breakout_retest`

## Non-Negotiables

- No config writes
- No env mutation
- No Binance/network calls
- No orders
- No executable or signed payloads
- No live execution
- No lane mode changes
- No `tiny_live` changes
- No risk contract config writes
- No signal-origin promotion
- No lane promotion
- No pattern live permissions

## Expected Output

- Pattern-origin x lane review packet
- Comparison against hammer/crows references
- Paper-only recommendations
- Explicit blocked retest-origin handling
- Safety object with order/live/network/config mutation false

## Validation

Run focused tests for the new R205 module and CLI, then related R204/R202/R200 matrix tests. Report safety invariants explicitly.
