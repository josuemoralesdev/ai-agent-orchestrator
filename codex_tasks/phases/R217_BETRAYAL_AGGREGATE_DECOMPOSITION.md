# R217 Betrayal Aggregate Decomposition

## Purpose

Decompose aggregate betrayal candidates into direction/entry-mode candidates using local evidence only, so future betrayal source rows can carry explicit `original_direction`, `inverse_direction`, `entry_mode`, source identity, event identity, and outcome windows.

## Scope

- Read R216 source emitter refresh output.
- Read R215 direction split resolver output.
- Read R212 event tracker output.
- Read R211/R210 betrayal context.
- Inspect local paper signals, shadow outcomes, true paper outcomes, and full-spectrum captures.
- Produce preview-only decomposition rows unless a future phase defines an exact append-only confirmation phrase.

## Safety

R217 must not:

- call Binance or network
- place orders
- create order payloads
- sign requests
- mutate env files
- mutate config files
- write risk contract config
- write lane config
- set any lane `tiny_live`
- disable the kill switch
- promote betrayal
- promote signal origins
- promote lanes
- authorize live execution
- fabricate original direction
- fabricate inverse direction
- fabricate outcomes
- destructively rewrite historical ledgers

## Expected Output

R217 should identify which aggregate candidates can be decomposed from explicit local evidence and which remain context-only:

- `222m aggregate`
- `88m aggregate`
- `55m aggregate` when available

Rows must remain paper-only and must clearly separate lane direction from source-proven original/inverse direction.
