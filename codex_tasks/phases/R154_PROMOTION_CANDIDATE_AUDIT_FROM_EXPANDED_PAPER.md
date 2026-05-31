# R154 Promotion Candidate Audit From Expanded Paper

## Phase

`R154`

## Branch

`r154-promotion-candidate-audit-from-expanded-paper`

## Phase Classification

- Primary classification: DIAGNOSTIC / AUDIT
- Secondary classification(s): WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY
- Duplicate risk level: HIGH

## Reason

R153 makes expanded BTCUSDT paper watch records observable across long/short and 4m/8m/13m/44m lane families. R154 should consume those records plus recent paper outcome statistics to identify which lane families deserve future tiny-live consideration.

## Main Objective

Build an audit-only promotion candidate report that ranks expanded paper lane families by fresh paper evidence and recent outcome quality without changing lane modes or creating live permission.

## Required Scope

- Read `logs/hammer_radar_forward/expanded_paper_watch.ndjson`.
- Read existing paper outcome/statistics ledgers already used by Hammer Radar strategy performance surfaces.
- Compare long versus short and 4m/8m/13m/44m families.
- Report candidate families that may deserve future operator review.
- Explicitly state that no lane mode promotion is performed.

## Safety Constraints

- Do not place real orders.
- Do not create executable Binance order payloads.
- Do not create protective order payloads.
- Do not call Binance order, test-order, protective, account, or private endpoints.
- Do not create signed request material.
- Do not mutate env files.
- Do not mutate `configs/hammer_radar/lane_controls.json`.
- Do not mutate global live flags.
- Do not disable the kill switch.
- Do not bypass R106/global gates.
- Do not set any new lane to `tiny_live`.
- Do not set any short lane to `tiny_live`.

## Expected Output

The R154 report should include:

- records checked
- lane families compared
- fresh paper evidence summary
- outcome stats summary
- promotion candidate ranking
- blockers and missing evidence
- recommended next operator move
- safe commands
- safety flags proving no live execution

## Validation

Add focused tests for:

- audit reads R153 records
- missing records are handled as blocked or waiting
- long/short/timeframe ranking is deterministic
- no lane config mutation
- no live commands
- safety flags remain clean
