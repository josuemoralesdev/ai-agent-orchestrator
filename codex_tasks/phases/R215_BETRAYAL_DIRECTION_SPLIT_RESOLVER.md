# R215 Betrayal Direction Split Resolver

## Purpose

Resolve aggregate betrayal candidates into direction-specific paper review rows where local paper evidence supports it.

Target candidates:

- `222m aggregate`
- `88m aggregate`
- `55m aggregate` if available

## Scope

Use local paper signals, local full-spectrum captures, R212 event tracker rows, R213 regime/Miro recheck output, R211 matrix context, and R210 true-inverse refresh only.

## Non-Negotiables

- No config writes.
- No env mutation.
- No lane mode changes.
- No risk contract writes.
- No Binance calls.
- No network calls.
- No order or test-order calls.
- No executable payloads.
- No signed requests.
- No live execution.
- No kill switch disable.
- No betrayal promotion.
- No signal-origin or lane promotion.
- No live authorization.

## Expected Output

Produce a paper-only direction split report that separates:

- original direction
- inverse direction
- entry mode
- source signal or capture identity
- event identity
- direction split confidence
- unresolved rows
- rows that remain aggregate context only
- hard live blockers

## Safety Result

R215 must preserve:

- `live_ready=false`
- `promotion_allowed=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `network_allowed=false`
- `betrayal_live_authorized=false`
- `betrayal_promoted=false`
