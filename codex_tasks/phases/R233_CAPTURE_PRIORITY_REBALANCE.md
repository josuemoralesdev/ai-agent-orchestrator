# R233 Capture Priority Rebalance

## Purpose

Use R232 enriched lane quality to recommend paper-only capture and fishing priorities.
This phase should help the operator decide which lanes deserve more paper capture attention without changing lane controls or promoting any lane.

## Scope

- Read the latest `logs/hammer_radar_forward/lane_outcome_enrichment.ndjson`.
- Read R231 scoreboard and capture-count sync context when useful.
- Recommend paper-only fishing priorities from:
  - combined watch score
  - outcome quality score
  - capture readiness gap
  - sample size bucket
  - outcome coverage
  - official lane context
- Keep the official tiny-live lane unchanged:

`BTCUSDT|8m|short|ladder_close_50_618`

## Non-Negotiable Safety

R233 must not:

- write configs unless explicitly requested in a later approved phase
- mutate env files
- write lane controls
- write risk contracts
- set any lane `tiny_live`
- promote any lane
- promote any signal origin
- call Binance or network
- create executable order payloads
- place orders
- transfer or withdraw
- disable the kill switch
- infer funding readiness
- infer live readiness
- authorize live execution

## Expected Output

R233 should produce a paper-only priority report with:

- official lane priority context
- top alternate lanes worth watching
- capture-blocked high-quality lanes
- lanes with weak or missing outcomes
- recommended fisherman/capture focus
- blockers
- `live_authorized=false`
- `promotion_allowed=false`
- safety flags proving no config/network/order/live action occurred

## Validation

Run focused tests for the R233 report and related R232/R231 tests.
Do not run network, Binance, order, protective, transfer, withdraw, sudo, commit, merge, or tag operations.
