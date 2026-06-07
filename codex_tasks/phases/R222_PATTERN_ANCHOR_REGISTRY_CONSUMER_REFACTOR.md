# R222 Pattern Anchor Registry Consumer Refactor

## Purpose

Wire pattern, anchor, and normal matrix surfaces to consume the R218 `strategy_evidence_registry` instead of maintaining independent candidate, timeframe, origin, anchor, or requirement lists.

## Scope

- Read the R218 strategy evidence registry.
- Prefer registry-backed timeframes for pattern outcome mapping and matrix reviews.
- Prefer registry-backed signal-origin manifests for Keter and lane matrix surfaces.
- Prefer registry-backed anchor type/period manifests for anchor preview and confluence surfaces.
- Produce compatibility and gap reports for remaining hardcoded target lists.
- Preserve current public outputs unless a registry-backed addition is explicitly report-only.

## Safety

- No config writes.
- No env writes or mutation.
- No live execution.
- No Binance/network calls.
- No order, test-order, or protective endpoint calls.
- No order payloads or signed requests.
- No live authorization.
- No signal-origin or lane promotion.
- No lane `tiny_live` mode changes.
- No risk contract config writes.

## Expected Validation

- Focused tests for the new registry consumer inventory/report.
- Existing R218 registry tests.
- Existing pattern, anchor, Keter, and lane matrix tests touched by the refactor.
- CLI preview and rejected/confirmed append-only recording smoke checks.
